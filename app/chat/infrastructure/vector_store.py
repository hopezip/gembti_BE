"""``chat_chunk`` 지식 테이블용 벡터 저장소 어댑터."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import math
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

from app.chat.infrastructure.embedding import (
    EmbeddingResponseError,
    validate_embedding_dimensions,
)
from app.chat.rag.model import (
    CHAT_CHUNK_EMBEDDING_DIMENSIONS,
    ChatChunkHit,
    RetrievalResult,
    parse_chat_chunk_source,
)

DEFAULT_SCORE_THRESHOLD = 0.0


@dataclass(frozen=True)
class ChatChunkVectorWrite:
    """DB가 ``id`` 등을 붙이기 전, ``chat_chunk`` 행에 쓸 페이로드."""

    content: str
    source: str
    embedding_vector: tuple[float, ...]

    def __post_init__(self) -> None:
        content = self.content.strip()
        if not content:
            raise ValueError("chat_chunk content must not be blank")
        parse_chat_chunk_source(self.source)
        vector = tuple(
            validate_embedding_dimensions(
                self.embedding_vector,
                expected_dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS,
            )
        )
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "embedding_vector", vector)


class ChatChunkVectorStore(Protocol):
    """답변 시점 고객센터 RAG용 벡터 검색 경계(인터페이스)."""

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 3,
        category_hint: str | None = None,
    ) -> list[RetrievalResult]:
        """유사도 상위 ``chat_chunk`` 벡터 히트를 반환한다."""

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        """임베딩된 청크를 지식 벡터 저장소에 삽입하거나 갱신(upsert)한다."""


class FakeChatChunkVectorStore:
    """네트워크 없는 테스트용 결정론적 인메모리 벡터 저장소.

    임베딩 간 코사인 유사도로만 점수를 매긴다. 의도적으로 벡터 기반이며,
    사용자 텍스트를 토큰화하거나 키워드 매칭을 수행하지 않는다.
    """

    def __init__(self, *, score_threshold: float = DEFAULT_SCORE_THRESHOLD) -> None:
        _validate_score_threshold(score_threshold)
        self.score_threshold = score_threshold
        self.entries: list[ChatChunkVectorWrite] = []
        self.search_calls: list[dict[str, object]] = []
        self.upsert_calls: list[list[ChatChunkVectorWrite]] = []

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        normalized_entries = list(entries)
        self.upsert_calls.append(normalized_entries)
        by_source = {entry.source: entry for entry in self.entries}
        for entry in normalized_entries:
            by_source[entry.source] = entry
        self.entries = list(by_source.values())

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 3,
        category_hint: str | None = None,
    ) -> list[RetrievalResult]:
        _validate_top_k(top_k)
        query_vector = validate_embedding_dimensions(
            query_embedding,
            expected_dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS,
        )
        self.search_calls.append(
            {
                "query_embedding": list(query_vector),
                "top_k": top_k,
                "category_hint": category_hint,
            }
        )

        scored: list[tuple[float, int, ChatChunkVectorWrite]] = []
        for position, entry in enumerate(self.entries):
            parsed = parse_chat_chunk_source(entry.source)
            if category_hint and parsed.category != category_hint:
                continue
            score = _normalized_cosine(query_vector, entry.embedding_vector)
            if score >= self.score_threshold:
                scored.append((score, position, entry))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievalResult(
                chunk=ChatChunkHit(content=entry.content, source=entry.source),
                score=score,
            )
            for score, _, entry in scored[:top_k]
        ]


class PgvectorChatChunkVectorStore:
    """실제 ``chat_chunk`` pgvector 테이블을 조회·저장하는 SQL 어댑터."""

    def __init__(
        self,
        session: Any,
        *,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> None:
        _validate_score_threshold(score_threshold)
        self._session = session
        self.score_threshold = score_threshold

    @staticmethod
    def build_similarity_query(*, include_category_hint: bool = False) -> str:
        """``chat_chunk.embedding_vector`` 유사도 검색에 쓰는 SQL을 만든다."""

        category_clause = ""
        if include_category_hint:
            category_clause = "\n  AND source LIKE :source_prefix"
        return f"""
SELECT id, content, source, 1 - (embedding_vector <=> :query_embedding) AS score
FROM chat_chunk
WHERE 1 - (embedding_vector <=> :query_embedding) >= :score_threshold{category_clause}
ORDER BY embedding_vector <=> :query_embedding
LIMIT :top_k
""".strip()

    @staticmethod
    def build_upsert_query() -> str:
        """``chat_chunk`` 행 삽입·갱신용 최소 insert/upsert SQL을 만든다."""

        return """
INSERT INTO chat_chunk (content, embedding_vector, source)
VALUES (:content, :embedding_vector, :source)
ON CONFLICT (source) DO UPDATE SET
  content = EXCLUDED.content,
  embedding_vector = EXCLUDED.embedding_vector
""".strip()

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        query = _sql_text(self.build_upsert_query())
        for entry in entries:
            self._session.execute(
                query,
                {
                    "content": entry.content,
                    "source": entry.source,
                    "embedding_vector": list(entry.embedding_vector),
                },
            )

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 3,
        category_hint: str | None = None,
    ) -> list[RetrievalResult]:
        _validate_top_k(top_k)
        query_vector = validate_embedding_dimensions(
            query_embedding,
            expected_dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS,
        )
        query = _sql_text(
            self.build_similarity_query(include_category_hint=category_hint is not None)
        )
        params: dict[str, Any] = {
            "query_embedding": query_vector,
            "score_threshold": self.score_threshold,
            "top_k": top_k,
        }
        if category_hint is not None:
            params["source_prefix"] = f"support.{category_hint}%#chunk-%"
        rows = self._session.execute(query, params)
        return [
            RetrievalResult(
                chunk=ChatChunkHit(
                    content=_row_value(row, "content"),
                    source=_row_value(row, "source"),
                ),
                score=float(_row_value(row, "score")),
            )
            for row in rows
        ]


def _validate_score_threshold(score_threshold: float) -> None:
    if not 0.0 <= score_threshold <= 1.0:
        raise ValueError("score_threshold must be between 0.0 and 1.0")


def _validate_top_k(top_k: int) -> None:
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")


def _normalized_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingResponseError("query and row embeddings must have the same dimension")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    cosine = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
    cosine /= left_norm * right_norm
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def _sql_text(sql: str) -> Any:
    try:
        sqlalchemy = importlib.import_module("sqlalchemy")
    except ImportError:
        return sql
    return sqlalchemy.text(sql)


def _row_value(row: Any, key: str) -> Any:
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping[key]
    if isinstance(row, dict):
        return row[key]
    return getattr(row, key)


__all__ = [
    "CHAT_CHUNK_EMBEDDING_DIMENSIONS",
    "ChatChunkVectorStore",
    "ChatChunkVectorWrite",
    "DEFAULT_SCORE_THRESHOLD",
    "FakeChatChunkVectorStore",
    "PgvectorChatChunkVectorStore",
]
