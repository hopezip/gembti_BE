"""고객지원 ``chat_chunk`` RAG 도메인 모델.

테이블 명세서(수정용 탭)의 ``chat_chunk``(content text, embedding_vector
vector(1536), source varchar(255), created_at timestamptz)와 REQ-CS-007이
고정한 MVP RAG 설정을 코드의 단일 진실원으로 보존한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_CHAT_CHUNK_SOURCE_PATTERN = re.compile(
    r"^(?P<doc_id>support\.(?P<category>[a-z][a-z0-9_]*)(?:\.[a-z][a-z0-9_-]*)*)"
    r"#chunk-(?P<chunk_index>\d{4})$"
)

CHAT_CHUNK_EMBEDDING_DIMENSIONS = 1536
CHAT_CHUNK_SOURCE_MAX_LENGTH = 255
CHAT_CHUNK_MAX_INDEX = 9999
RETRIEVAL_SCORE_TOLERANCE = 1e-9

ALLOWED_SUPPORT_CATEGORIES = frozenset(
    {
        "account",
        "steam",
        "survey",
        "preference_profile",
        "recommendation",
        "game",
        "community",
        "policy",
        "troubleshooting",
        "general",
    }
)


@dataclass(frozen=True)
class SupportRagSettings:
    """REQ-CS-007이 고정한 고객센터 RAG MVP 색인/검색 설정.

    요구사항 변경표(2026-05-27/29) 확정값: OpenAI ``text-embedding-3-small``
    1536차원, chunk 1000/overlap 150, pgvector cosine, top_k=3,
    score_threshold=0.37(= cosine distance 0.63 이하). 고객센터 도움말 RAG는
    설문/추천/게임 근거 RAG와 분리하며, MVP에서는 전용 ``chat_chunk`` 테이블과
    ``support.*`` doc_id 접두사로 그 경계를 유지한다.
    """

    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = CHAT_CHUNK_EMBEDDING_DIMENSIONS
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 3
    score_threshold: float = 0.37

    def __post_init__(self) -> None:
        if not self.embedding_model.strip():
            raise ValueError("embedding_model must not be blank")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if not 0.0 <= self.score_threshold <= 1.0:
            raise ValueError("score_threshold must be between 0.0 and 1.0")

    @property
    def max_cosine_distance(self) -> float:
        """pgvector cosine distance 컷오프(= 1 - score_threshold)."""
        return 1.0 - self.score_threshold


SUPPORT_RAG_SETTINGS = SupportRagSettings()


@dataclass(frozen=True)
class ParsedChunkSource:
    """파싱·정규화된 ``chat_chunk.source``."""

    source: str
    doc_id: str
    category: str
    chunk_index: int


@dataclass(frozen=True)
class SupportHelpMetadata:
    """도움말 frontmatter 메타데이터."""

    doc_id: str
    title: str
    category: str
    status: str
    visibility: str
    tags: tuple[str, ...]
    updated_at: str
    reviewed_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))


SourceDocumentMetadata = SupportHelpMetadata


@dataclass(frozen=True)
class SupportHelpDocument:
    """청킹 전 도움말 문서."""

    metadata: SupportHelpMetadata
    body: str
    source_path: str
    sections: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", dict(self.sections))


@dataclass(frozen=True)
class ChatChunkDraft:
    """DB 저장 전 ``chat_chunk`` 초안."""

    content: str
    source: str

    def __post_init__(self) -> None:
        content = self.content.strip()
        if not content:
            raise ValueError("chat_chunk content must not be blank")
        parsed = parse_chat_chunk_source(self.source)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "source", parsed.source)


@dataclass(frozen=True)
class ChatChunkRecord:
    """저장된 ``chat_chunk`` 행."""

    id: int
    content: str
    embedding_vector: tuple[float, ...]
    source: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("chat_chunk id must be positive")
        content = self.content.strip()
        if not content:
            raise ValueError("chat_chunk content must not be blank")
        vector = validate_embedding_vector(self.embedding_vector)
        parsed = parse_chat_chunk_source(self.source)
        if not isinstance(self.created_at, datetime):
            raise ValueError("chat_chunk created_at must be a datetime")
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "embedding_vector", vector)
        object.__setattr__(self, "source", parsed.source)


@dataclass(frozen=True)
class CitationMetadata:
    """인용 UI용 메타데이터."""

    source: str
    doc_id: str
    title: str
    category: str
    source_path: str
    section: str

    def __post_init__(self) -> None:
        parsed = parse_chat_chunk_source(self.source)
        if parsed.doc_id != self.doc_id:
            raise ValueError("citation doc_id must match chat_chunk.source")
        if parsed.category != self.category:
            raise ValueError("citation category must match chat_chunk.source")
        for field_name in ("title", "source_path", "section"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"citation {field_name} must not be blank")
        object.__setattr__(self, "source", parsed.source)


@dataclass(frozen=True)
class SupportHelpChunk:
    """임베딩 전 소스 청크."""

    doc_id: str
    title: str
    category: str
    source_path: str
    section: str
    content: str
    source: str

    def __post_init__(self) -> None:
        parsed = parse_chat_chunk_source(self.source)
        if parsed.doc_id != self.doc_id:
            raise ValueError("chunk doc_id must match chat_chunk.source")
        if parsed.category != self.category:
            raise ValueError("chunk category must match chat_chunk.source")
        content = self.content.strip()
        if not content:
            raise ValueError("chunk content must not be blank")
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "source", parsed.source)

    def to_chat_chunk_draft(self) -> ChatChunkDraft:
        """DB 저장용 초안을 반환한다."""
        return ChatChunkDraft(content=self.content, source=self.source)

    def to_citation_metadata(self) -> CitationMetadata:
        """인용 메타데이터를 반환한다."""
        return CitationMetadata(
            source=self.source,
            doc_id=self.doc_id,
            title=self.title,
            category=self.category,
            source_path=self.source_path,
            section=self.section,
        )


@dataclass(frozen=True)
class ChatChunkHit:
    """벡터 검색으로 반환된 ``chat_chunk``."""

    content: str
    source: str
    id: int | None = None
    citation: CitationMetadata | None = None
    parsed_source: ParsedChunkSource = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        content = self.content.strip()
        if not content:
            raise ValueError("retrieved chat_chunk content must not be blank")
        if self.id is not None and self.id <= 0:
            raise ValueError("retrieved chat_chunk id must be positive")
        parsed = parse_chat_chunk_source(self.source)
        object.__setattr__(self, "source", parsed.source)
        object.__setattr__(self, "parsed_source", parsed)
        if self.citation is not None and self.citation.source != self.source:
            raise ValueError("citation source must match retrieved chat_chunk source")
        object.__setattr__(self, "content", content)

    @property
    def doc_id(self) -> str:
        return self.parsed_source.doc_id

    @property
    def category(self) -> str:
        return self.parsed_source.category

    @property
    def title(self) -> str:
        return self.citation.title if self.citation is not None else self.doc_id

    @property
    def source_path(self) -> str:
        return self.citation.source_path if self.citation is not None else "unknown"

    @property
    def section(self) -> str:
        if self.citation is not None:
            return self.citation.section
        return f"chunk-{self.parsed_source.chunk_index:04d}"


@dataclass(frozen=True)
class RetrievalResult:
    """정규화 점수가 포함된 검색 결과."""

    chunk: ChatChunkHit
    score: float

    def __post_init__(self) -> None:
        score = float(self.score)
        if not (-RETRIEVAL_SCORE_TOLERANCE <= score <= 1.0 + RETRIEVAL_SCORE_TOLERANCE):
            raise ValueError("RetrievalResult score must be normalized between 0.0 and 1.0")
        object.__setattr__(self, "score", min(max(score, 0.0), 1.0))

    def meets_threshold(self, threshold: float = SUPPORT_RAG_SETTINGS.score_threshold) -> bool:
        """점수가 검색 컷오프(threshold) 이상인지 반환한다."""
        return self.score >= threshold


class MetadataValidationError(ValueError):
    """도움말 메타데이터 검증 실패."""

    source_path: str
    problems: tuple[str, ...]

    def __init__(self, source_path: str, problems: list[str] | tuple[str, ...]) -> None:
        self.source_path = source_path
        self.problems = tuple(problems)
        detail = "; ".join(self.problems) or "unknown metadata problem"
        super().__init__(f"Invalid support-help metadata in {source_path}: {detail}")


def format_chat_chunk_source(doc_id: str, chunk_index: int) -> str:
    """doc_id와 청크 인덱스로 source 문자열을 만든다."""
    if chunk_index <= 0:
        raise ValueError("chunk_index must be positive")
    if chunk_index > CHAT_CHUNK_MAX_INDEX:
        raise ValueError(f"chunk_index must be at most {CHAT_CHUNK_MAX_INDEX}")
    source = f"{doc_id}#chunk-{chunk_index:04d}"
    parse_chat_chunk_source(source)
    return source


def validate_embedding_vector(
    vector: Iterable[float],
    *,
    expected_dimensions: int = CHAT_CHUNK_EMBEDDING_DIMENSIONS,
) -> tuple[float, ...]:
    """임베딩 벡터의 숫자/차원/유한성을 검증하고 tuple로 정규화한다."""
    try:
        normalized = tuple(float(value) for value in vector)
    except (TypeError, ValueError) as exc:
        raise ValueError("embedding vector must contain numeric values") from exc
    if len(normalized) != expected_dimensions:
        raise ValueError(
            f"embedding vector must have {expected_dimensions} dimensions, got {len(normalized)}"
        )
    if any(not math.isfinite(value) for value in normalized):
        raise ValueError("embedding vector must contain only finite values")
    return normalized


def parse_chat_chunk_source(source: str) -> ParsedChunkSource:
    """source 문자열을 파싱·검증하고 정규화된 결과를 반환한다."""
    normalized_source = source.strip()
    if len(normalized_source) > CHAT_CHUNK_SOURCE_MAX_LENGTH:
        raise ValueError(
            f"chat_chunk source must be at most {CHAT_CHUNK_SOURCE_MAX_LENGTH} characters"
        )
    match = _CHAT_CHUNK_SOURCE_PATTERN.match(normalized_source)
    if match is None:
        raise ValueError("chat_chunk source must use doc_id#chunk-NNNN format")
    chunk_index = int(match.group("chunk_index"))
    if chunk_index <= 0:
        raise ValueError("chat_chunk chunk index must be positive")
    category = match.group("category")
    if category not in ALLOWED_SUPPORT_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_SUPPORT_CATEGORIES))
        raise ValueError(f"chat_chunk source category must be one of: {allowed}")
    return ParsedChunkSource(
        source=normalized_source,
        doc_id=match.group("doc_id"),
        category=category,
        chunk_index=chunk_index,
    )


__all__ = [
    "ChatChunkDraft",
    "ChatChunkHit",
    "ChatChunkRecord",
    "CHAT_CHUNK_EMBEDDING_DIMENSIONS",
    "CHAT_CHUNK_MAX_INDEX",
    "CHAT_CHUNK_SOURCE_MAX_LENGTH",
    "CitationMetadata",
    "ALLOWED_SUPPORT_CATEGORIES",
    "MetadataValidationError",
    "ParsedChunkSource",
    "RETRIEVAL_SCORE_TOLERANCE",
    "RetrievalResult",
    "SourceDocumentMetadata",
    "SUPPORT_RAG_SETTINGS",
    "SupportHelpChunk",
    "SupportHelpDocument",
    "SupportHelpMetadata",
    "SupportRagSettings",
    "format_chat_chunk_source",
    "parse_chat_chunk_source",
    "validate_embedding_vector",
]
