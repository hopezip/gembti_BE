# =============================================================================
# [모듈 개요] app/chat/infrastructure/vector_store.py
#
# 책임: 고객센터 RAG의 **벡터 저장·검색** 경계(adapter) 모듈.
#   - embedding.py가 만든 숫자 벡터(embedding_vector)를 **저장(upsert)** 하고,
#     질문 벡터(query_embedding)와 **가장 가까운 chat_chunk** 를 **검색(search)** 한다.
#   - "벡터 스토어"란? 문장을 좌표로 본 뒤, 비슷한 좌표(의미가 가까운 청크)를 찾는 저장소.
#
# 흐름(파이프라인):
#   [인덱싱]
#   docs/help/support/*.md
#       → rag/service.py SupportKnowledgeIndexer.index_corpus()
#       → embedding.py embed_text(chunk.content)
#       → ChatChunkVectorWrite 생성(이 파일)
#       → vector_store.upsert() → chat_chunk 테이블(pgvector) 또는 Fake 메모리
#
#   [검색]
#   사용자 질문
#       → rag/service.py SupportRagService.retrieve()
#       → embedding.py embed_text(question) → query_embedding
#       → vector_store.search() → list[RetrievalResult]
#       → cs/service.py → llm.py 답변 생성
#
# 왜 infrastructure 경계인가?
#   rag/service.py는 "언제 임베딩·언제 검색할지"만 알고,
#   DB(pgvector) vs 메모리(Fake) 구현 세부는 이 파일에 숨긴다(의존성 주입).
#
# 다른 선택지:
#   - InMemorySupportVectorStore(어휘/토큰 매칭) → 제거됨(test_vector_store.py가 확인).
#     키워드만 맞추면 의미 검색 품질이 낮아, MVP 이후 벡터 기반으로 전환한 것으로 보인다.
#   - Pinecone / Weaviate / Qdrant 등 외부 벡터 DB → 운영 확장 시 후보, 지금은 PostgreSQL pgvector
#   - Elasticsearch dense_vector → 별도 인프라 필요
#   - search 시 원문 토큰화 후 BM25 → 이 모듈은 **임베딩 코사인**만 담당(Fake docstring 명시)
#
# 이 구현을 택한 근거:
#   - ChatChunkVectorStore(Protocol)로 Fake/Pgvector 교체 → network-free 테스트 유지
#   - SQL을 build_similarity_query()로 분리 → test가 DB 없이 쿼리 문자열만 검증 가능
#   - source UNIQUE + ON CONFLICT upsert → 같은 청크 재인덱싱 시 덮어쓰기
#
# 가장 기본적인 코드인가?
#   아니다. Protocol, frozen dataclass 검증, pgvector <=> 연산자, 코사인 [0,1] 정규화,
#   lazy sqlalchemy import 등이 들어 있다. 최소는 dict[source, vector] + for 루프 검색.
# =============================================================================
"""``chat_chunk`` 지식 테이블용 벡터 저장소 어댑터."""

from __future__ import annotations  # 타입 힌트 지연 평가

from dataclasses import dataclass  # ChatChunkVectorWrite: 불변 데이터 객체
import importlib  # sqlalchemy를 런타임에만 로드(테스트·network-free 경계)
import math  # 코사인 유사도 계산(sqrt, norm)
from typing import TYPE_CHECKING, Any, Protocol  # Protocol: 벡터 스토어 계약

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence  # 타입 검사기 전용 — 런타임 import 부담 없음

from app.chat.infrastructure.embedding import (
    EmbeddingResponseError,
)
from app.chat.infrastructure.embedding import (
    validate_embedding_dimensions,  # upsert/search 직전 차원·유한수 검증
)
from app.chat.rag.model import (
    CHAT_CHUNK_EMBEDDING_DIMENSIONS,
    ChatChunkHit,
    RetrievalResult,
    parse_chat_chunk_source,
)

# 검색 결과로 취급할 최소 코사인 점수(0~1 스케일). 0.0이면 모든 hit 허용.
DEFAULT_SCORE_THRESHOLD = 0.0


# =============================================================================
# ChatChunkVectorWrite
#
# 역할: chat_chunk 행에 넣기 **직전** 페이로드. DB가 아직 id를 안 붙인 상태의 쓰기 단위.
#
# 입력: content, source(예: support.steam#chunk-0001), embedding_vector(1536차원)
# 출력/사용처:
#   - rag/service.py SupportKnowledgeIndexer.index_corpus() 가 생성
#   - FakeChatChunkVectorStore.upsert / PgvectorChatChunkVectorStore.upsert
# =============================================================================
@dataclass(frozen=True)  # frozen=True: 생성 후 필드 변경 불가 — 해시·불변 계약
class ChatChunkVectorWrite:
    """DB가 ``id`` 등을 붙이기 전, ``chat_chunk`` 행에 쓸 페이로드."""

    content: str
    source: str
    embedding_vector: tuple[float, ...]  # tuple: 불변·해시 가능(리스트보다 저장소 키로 안전)

    def __post_init__(self) -> None:
        # dataclass 생성 직후 검증 — 잘못된 행이 vector_store/DB로 넘어가기 전에 차단
        content = self.content.strip()
        if not content:
            raise ValueError("chat_chunk content must not be blank")
        parse_chat_chunk_source(self.source)  # source 형식이 support.{cat}#chunk-NNNN 인지 검사
        vector = tuple(
            validate_embedding_dimensions(
                self.embedding_vector,
                expected_dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS,
            )
        )
        # frozen dataclass는 일반 대입 불가 → object.__setattr__로 정규화된 값만 반영(백도어)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "embedding_vector", vector)


# =============================================================================
# ChatChunkVectorStore (Protocol)
#
# 역할: "search + upsert" 만 있으면 벡터 저장소로 인정하는 계약.
#   embedding.py EmbeddingClient, llm.py SupportResponder 와 같은 교체 가능 경계 패턴.
#
# 사용처: rag/service.py 가 vector_store: ChatChunkVectorStore 로 주입
#   - 기본/테스트: FakeChatChunkVectorStore
#   - 운영: PgvectorChatChunkVectorStore(session)
# =============================================================================
class ChatChunkVectorStore(Protocol):
    """답변 시점 고객센터 RAG용 벡터 검색 경계(인터페이스)."""

    def search(
        self,
        query_embedding: Sequence[float],  # 질문 임베딩(이미 embedding.py에서 생성됨)
        *,
        top_k: int = 3,
        category_hint: str | None = None,  # 예: "steam" — source 카테고리 필터
    ) -> list[RetrievalResult]:
        """유사도 상위 ``chat_chunk`` 벡터 히트를 반환한다."""

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        """임베딩된 청크를 지식 벡터 저장소에 삽입하거나 갱신(upsert)한다."""


# =============================================================================
# FakeChatChunkVectorStore
#
# 역할: 메모리 안에서 코사인 유사도로 검색하는 **가짜** 벡터 DB. 네트워크·PostgreSQL 불필요.
#   토큰/키워드 매칭은 하지 않음(test_fake_vector_store_ranks_by_embedding_similarity_not_tokens).
#
# 테스트 보조:
#   search_calls, upsert_calls — 호출 인자를 기록해 test_rag_service가 "임베딩만 넘겼는지" 검증
#
# 사용처: rag/service.py 기본값, tests/chat/test_vector_store.py, test_rag_service.py
# =============================================================================
class FakeChatChunkVectorStore:
    """네트워크 없는 테스트용 결정론적 인메모리 벡터 저장소.

    임베딩 간 코사인 유사도로만 점수를 매긴다. 의도적으로 벡터 기반이며,
    사용자 텍스트를 토큰화하거나 키워드 매칭을 수행하지 않는다.
    """

    def __init__(self, *, score_threshold: float = DEFAULT_SCORE_THRESHOLD) -> None:
        _validate_score_threshold(score_threshold)
        self.score_threshold = score_threshold
        self.entries: list[ChatChunkVectorWrite] = []
        self.search_calls: list[dict[str, object]] = []  # 테스트 스파이: search 호출 이력
        self.upsert_calls: list[list[ChatChunkVectorWrite]] = []

    def upsert(self, entries: Iterable[ChatChunkVectorWrite]) -> None:
        normalized_entries = list(entries)
        self.upsert_calls.append(normalized_entries)
        # source를 키로 같은 청크는 덮어쓰기(실 DB ON CONFLICT 와 동일 의미)
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
            # category_hint가 있으면 support.{hint} 카테고리만 후보로 남김
            if category_hint and parsed.category != category_hint:
                continue
            score = _normalized_cosine(query_vector, entry.embedding_vector)
            if score >= self.score_threshold:
                scored.append((score, position, entry))

        # 점수 내림차순, 동점이면 먼저 들어온 position(안정 정렬)
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievalResult(
                chunk=ChatChunkHit(content=entry.content, source=entry.source),
                score=score,
            )
            for score, _, entry in scored[:top_k]
        ]


# =============================================================================
# PgvectorChatChunkVectorStore
#
# 역할: PostgreSQL + pgvector 확장의 chat_chunk 테이블에 대한 **운영용** SQL 어댑터.
#
# 핵심 SQL:
#   embedding_vector <=> :query_embedding  — pgvector 코사인 **거리**(작을수록 유사)
#   1 - (거리)  — 유사도 점수로 변환(0~1에 가깝게 사용)
#
# 사용처: rag/service.py build_runtime_support_rag_service(session)
# =============================================================================
class PgvectorChatChunkVectorStore:
    """실제 ``chat_chunk`` pgvector 테이블을 조회·저장하는 SQL 어댑터."""

    def __init__(
        self,
        session: Any,  # SQLAlchemy Session 등 — 구체 타입은 DB 승인 후 고정 가능
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
            # source가 support.steam%#chunk-% 형태인 행만 — Fake의 category 필터와 대응
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
                    "embedding_vector": list(
                        entry.embedding_vector
                    ),  # DB 드라이버는 list 선호하는 경우 많음
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


# =============================================================================
# 내부 헬퍼 (_ 접두사)
#
# 왜 _ 접두사? 모듈 공개 API는 Protocol·Store 클래스·ChatChunkVectorWrite 뿐.
# =============================================================================
def _validate_score_threshold(score_threshold: float) -> None:
    if not 0.0 <= score_threshold <= 1.0:
        raise ValueError("score_threshold must be between 0.0 and 1.0")


def _validate_top_k(top_k: int) -> None:
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")


def _normalized_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    # 표준 코사인 유사도(-1~1)를 0~1 구간으로 선형 변환 — cs/service confidence와 스케일 맞춤
    if len(left) != len(right):
        raise EmbeddingResponseError("query and row embeddings must have the same dimension")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0  # 영벡터는 방향이 없어 유사도 0
    cosine = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
    cosine /= left_norm * right_norm
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def _sql_text(sql: str) -> Any:
    # sqlalchemy 없는 환경(일부 테스트)에서는 raw str 반환 — import 실패로 전체 모듈이 깨지지 않게
    try:
        sqlalchemy = importlib.import_module("sqlalchemy")
    except ImportError:
        return sql
    return sqlalchemy.text(sql)  # 바인드 파라미터 :query_embedding 등을 안전하게 실행


def _row_value(row: Any, key: str) -> Any:
    # SQLAlchemy Row / dict / 객체 등 다양한 row 형태에서 컬럼 값 추출
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping[key]
    if isinstance(row, dict):
        return row[key]
    return getattr(row, key)


# CHAT_CHUNK_EMBEDDING_DIMENSIONS는 rag.model에서 import되어 재export
__all__ = [
    "CHAT_CHUNK_EMBEDDING_DIMENSIONS",
    "ChatChunkVectorStore",
    "ChatChunkVectorWrite",
    "DEFAULT_SCORE_THRESHOLD",
    "FakeChatChunkVectorStore",
    "PgvectorChatChunkVectorStore",
]
