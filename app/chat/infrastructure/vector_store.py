"""``chat_chunk`` 지식 테이블용 벡터 저장소 어댑터."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import math
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable, Sequence

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
from app.chat.rag.query import (
    SupportQueryAnalysis,
    compact_support_text,
    normalize_support_text,
)

if TYPE_CHECKING:
    VectorSearchResult = list[RetrievalResult] | Awaitable[list[RetrievalResult]]
    VectorUpsertResult = None | Awaitable[None]

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
    ) -> VectorSearchResult:
        """유사도 상위 ``chat_chunk`` 벡터 히트를 반환한다."""

    def search_lexical(
        self,
        analysis: SupportQueryAnalysis,
        *,
        top_k: int = 3,
    ) -> VectorSearchResult:
        """긴급 임시 lexical recovery 결과를 반환한다."""

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> VectorUpsertResult:
        """임베딩된 청크를 지식 벡터 저장소에 삽입하거나 갱신(upsert)한다."""

    def replace_support_corpus(
        self,
        entries: Iterable[ChatChunkVectorWrite],
    ) -> VectorUpsertResult:
        """기존 고객센터 support 청크를 현재 적재 목록으로 교체한다."""


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

    def replace_support_corpus(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        normalized_entries = list(entries)
        self.upsert_calls.append(normalized_entries)
        self.entries = normalized_entries

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

    def search_lexical(
        self,
        analysis: SupportQueryAnalysis,
        *,
        top_k: int = 3,
    ) -> list[RetrievalResult]:
        _validate_top_k(top_k)
        if not analysis.allows_lexical_recovery:
            return []

        scored: list[tuple[float, int, ChatChunkVectorWrite]] = []
        for position, entry in enumerate(self.entries):
            score = _temporary_lexical_score(
                content=entry.content,
                source=entry.source,
                analysis=analysis,
            )
            if score > 0:
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
SELECT id, content, source, 1 - (embedding_vector <=> CAST(:query_embedding AS vector)) AS score
FROM chat_chunk
WHERE embedding_vector IS NOT NULL
  AND source IS NOT NULL
  AND 1 - (embedding_vector <=> CAST(:query_embedding AS vector)) >= :score_threshold{category_clause}
ORDER BY embedding_vector <=> CAST(:query_embedding AS vector)
LIMIT :top_k
""".strip()

    @staticmethod
    def build_delete_by_source_query() -> str:
        """명세에 없는 unique 제약 없이 ``source`` 기준 기존 행을 제거한다."""

        return """
DELETE FROM chat_chunk
WHERE source = :source
""".strip()

    @staticmethod
    def build_delete_support_corpus_query() -> str:
        """현재 고객센터 support corpus를 다시 적재하기 전 기존 support 청크를 제거한다."""

        return """
DELETE FROM chat_chunk
WHERE source LIKE 'support.%#chunk-%'
""".strip()

    @staticmethod
    def build_insert_query() -> str:
        """``chat_chunk`` 행 삽입 SQL을 만든다."""

        return """
INSERT INTO chat_chunk (content, embedding_vector, source)
VALUES (:content, CAST(:embedding_vector AS vector), :source)
""".strip()

    @staticmethod
    def build_lexical_candidate_query() -> str:
        """긴급 임시 lexical recovery용 후보 행을 가져온다."""

        return """
SELECT id, content, source
FROM chat_chunk
WHERE content IS NOT NULL
  AND source IS NOT NULL
ORDER BY id ASC
LIMIT :candidate_limit
""".strip()

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> VectorUpsertResult:
        delete_query = _sql_text(self.build_delete_by_source_query())
        insert_query = _sql_text(self.build_insert_query())
        for entry in entries:
            self._session.execute(delete_query, {"source": entry.source})
            self._session.execute(
                insert_query,
                {
                    "content": entry.content,
                    "source": entry.source,
                    "embedding_vector": _pgvector_literal(entry.embedding_vector),
                },
            )
        return None

    def replace_support_corpus(self, entries: Iterable[ChatChunkVectorWrite]) -> VectorUpsertResult:
        self._session.execute(_sql_text(self.build_delete_support_corpus_query()))
        insert_query = _sql_text(self.build_insert_query())
        for entry in entries:
            self._session.execute(
                insert_query,
                {
                    "content": entry.content,
                    "source": entry.source,
                    "embedding_vector": _pgvector_literal(entry.embedding_vector),
                },
            )
        return None

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 3,
        category_hint: str | None = None,
    ) -> VectorSearchResult:
        _validate_top_k(top_k)
        query_vector = validate_embedding_dimensions(
            query_embedding,
            expected_dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS,
        )
        query = _sql_text(
            self.build_similarity_query(include_category_hint=category_hint is not None)
        )
        params: dict[str, Any] = {
            "query_embedding": _pgvector_literal(query_vector),
            "score_threshold": self.score_threshold,
            "top_k": top_k,
        }
        if category_hint is not None:
            params["source_prefix"] = f"support.{category_hint}%#chunk-%"
        rows = self._session.execute(query, params)
        return [
            RetrievalResult(
                chunk=ChatChunkHit(
                    id=int(_row_value(row, "id")),
                    content=_row_value(row, "content"),
                    source=_row_value(row, "source"),
                ),
                score=float(_row_value(row, "score")),
            )
            for row in rows
        ]

    def search_lexical(
        self,
        analysis: SupportQueryAnalysis,
        *,
        top_k: int = 3,
    ) -> VectorSearchResult:
        _validate_top_k(top_k)
        if not analysis.allows_lexical_recovery:
            return []

        rows = self._session.execute(
            _sql_text(self.build_lexical_candidate_query()),
            {"candidate_limit": _lexical_candidate_limit(top_k)},
        )
        return _build_lexical_results(rows, analysis=analysis, top_k=top_k)


class AsyncPgvectorChatChunkVectorStore(PgvectorChatChunkVectorStore):
    """비동기 SQLAlchemy 세션으로 ``chat_chunk`` pgvector를 조회·저장하는 어댑터."""

    async def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        delete_query = _sql_text(self.build_delete_by_source_query())
        insert_query = _sql_text(self.build_insert_query())
        for entry in entries:
            await self._session.execute(delete_query, {"source": entry.source})
            await self._session.execute(
                insert_query,
                {
                    "content": entry.content,
                    "source": entry.source,
                    "embedding_vector": _pgvector_literal(entry.embedding_vector),
                },
            )

    async def replace_support_corpus(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        await self._session.execute(_sql_text(self.build_delete_support_corpus_query()))
        insert_query = _sql_text(self.build_insert_query())
        for entry in entries:
            await self._session.execute(
                insert_query,
                {
                    "content": entry.content,
                    "source": entry.source,
                    "embedding_vector": _pgvector_literal(entry.embedding_vector),
                },
            )

    async def search(
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
            "query_embedding": _pgvector_literal(query_vector),
            "score_threshold": self.score_threshold,
            "top_k": top_k,
        }
        if category_hint is not None:
            params["source_prefix"] = f"support.{category_hint}%#chunk-%"
        rows = await self._session.execute(query, params)
        return [
            RetrievalResult(
                chunk=ChatChunkHit(
                    id=int(_row_value(row, "id")),
                    content=_row_value(row, "content"),
                    source=_row_value(row, "source"),
                ),
                score=float(_row_value(row, "score")),
            )
            for row in rows
        ]

    async def search_lexical(
        self,
        analysis: SupportQueryAnalysis,
        *,
        top_k: int = 3,
    ) -> list[RetrievalResult]:
        _validate_top_k(top_k)
        if not analysis.allows_lexical_recovery:
            return []

        rows = await self._session.execute(
            _sql_text(self.build_lexical_candidate_query()),
            {"candidate_limit": _lexical_candidate_limit(top_k)},
        )
        return _build_lexical_results(rows, analysis=analysis, top_k=top_k)


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


def _temporary_lexical_score(
    *,
    content: str,
    source: str,
    analysis: SupportQueryAnalysis,
) -> float:
    """기존 dense 검색을 보강하는 임시 lexical 점수를 계산한다."""

    haystack = f"{source} {content}"
    normalized_haystack = normalize_support_text(haystack)
    compact_haystack = compact_support_text(haystack)
    score = 0.0

    if len(analysis.normalized_text) >= 2 and analysis.normalized_text in normalized_haystack:
        score = max(score, 0.75)
    if len(analysis.compact_text) >= 2 and analysis.compact_text in compact_haystack:
        score = max(score, 0.70)

    normalized_terms = tuple(normalize_support_text(term) for term in analysis.support_terms)
    compact_terms = tuple(compact_support_text(term) for term in analysis.support_terms)
    if normalized_terms and all(
        term in normalized_haystack or compact_term in compact_haystack
        for term, compact_term in zip(normalized_terms, compact_terms, strict=True)
    ):
        score = max(score, 0.60)

    if score <= 0:
        return 0.0

    try:
        category = parse_chat_chunk_source(source).category
    except ValueError:
        return score
    if category in analysis.category_hints:
        score += 0.05
    return min(score, 1.0)


def _build_lexical_results(
    rows: Iterable[Any],
    *,
    analysis: SupportQueryAnalysis,
    top_k: int,
) -> list[RetrievalResult]:
    scored: list[tuple[float, int, ChatChunkHit]] = []
    for position, row in enumerate(rows):
        content = _row_value(row, "content")
        source = _row_value(row, "source")
        score = _temporary_lexical_score(
            content=content,
            source=source,
            analysis=analysis,
        )
        if score <= 0:
            continue
        try:
            chunk = ChatChunkHit(
                id=int(_row_value(row, "id")),
                content=content,
                source=source,
            )
        except ValueError:
            continue
        scored.append((score, position, chunk))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [RetrievalResult(chunk=chunk, score=score) for score, _, chunk in scored[:top_k]]


def _lexical_candidate_limit(top_k: int) -> int:
    return max(200, top_k * 50)


def _pgvector_literal(vector: Sequence[float]) -> str:
    normalized = validate_embedding_dimensions(
        vector,
        expected_dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS,
    )
    return f"[{','.join(str(value) for value in normalized)}]"


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
    "AsyncPgvectorChatChunkVectorStore",
    "CHAT_CHUNK_EMBEDDING_DIMENSIONS",
    "ChatChunkVectorStore",
    "ChatChunkVectorWrite",
    "DEFAULT_SCORE_THRESHOLD",
    "FakeChatChunkVectorStore",
    "PgvectorChatChunkVectorStore",
]
