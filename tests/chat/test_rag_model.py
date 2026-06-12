"""chat_chunk source 정규화 회귀 테스트."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from app.chat.rag.model import (
    CHAT_CHUNK_EMBEDDING_DIMENSIONS,
    CHAT_CHUNK_MAX_INDEX,
    SUPPORT_RAG_SETTINGS,
    ChatChunkDraft,
    ChatChunkHit,
    ChatChunkRecord,
    CitationMetadata,
    RetrievalResult,
    SupportHelpChunk,
    SupportHelpDocument,
    SupportHelpMetadata,
    format_chat_chunk_source,
    parse_chat_chunk_source,
    validate_embedding_vector,
)

CLEAN_SOURCE = "support.account#chunk-0001"
PADDED_SOURCE = f"  {CLEAN_SOURCE}  "
CREATED_AT = datetime(2026, 6, 1, tzinfo=UTC)


def test_parse_chat_chunk_source_returns_normalized_source() -> None:
    parsed = parse_chat_chunk_source(PADDED_SOURCE)

    assert parsed.source == CLEAN_SOURCE


def test_chat_chunk_draft_strips_source_before_storing() -> None:
    draft = ChatChunkDraft(content="x", source=PADDED_SOURCE)

    assert draft.source == CLEAN_SOURCE


def test_chat_chunk_record_strips_source_before_storing() -> None:
    record = ChatChunkRecord(
        id=1,
        content="x",
        embedding_vector=(0.0,) * CHAT_CHUNK_EMBEDDING_DIMENSIONS,
        source=PADDED_SOURCE,
        created_at=CREATED_AT,
    )

    assert record.source == CLEAN_SOURCE


def test_chat_chunk_record_rejects_non_datetime_created_at() -> None:
    with pytest.raises(ValueError, match="created_at must be a datetime"):
        ChatChunkRecord(
            id=1,
            content="x",
            embedding_vector=(0.0,) * CHAT_CHUNK_EMBEDDING_DIMENSIONS,
            source=CLEAN_SOURCE,
            created_at=None,  # type: ignore[arg-type]
        )


def test_citation_metadata_strips_source_before_storing() -> None:
    citation = CitationMetadata(
        source=PADDED_SOURCE,
        doc_id="support.account",
        title="Account help",
        category="account",
        source_path="docs/help/support/account.md",
        section="Intro",
    )

    assert citation.source == CLEAN_SOURCE


def test_support_help_chunk_strips_source_before_storing() -> None:
    chunk = SupportHelpChunk(
        doc_id="support.account",
        title="Account help",
        category="account",
        source_path="docs/help/support/account.md",
        section="Intro",
        content="x",
        source=PADDED_SOURCE,
    )

    assert chunk.source == CLEAN_SOURCE


def test_chat_chunk_hit_with_padded_source_matches_normalized_citation() -> None:
    citation = CitationMetadata(
        source=CLEAN_SOURCE,
        doc_id="support.account",
        title="Account help",
        category="account",
        source_path="docs/help/support/account.md",
        section="Intro",
    )

    hit = ChatChunkHit(content="x", source=PADDED_SOURCE, citation=citation)

    assert hit.source == CLEAN_SOURCE
    assert hit.citation is not None
    assert hit.citation.source == hit.source


def _make_hit() -> ChatChunkHit:
    return ChatChunkHit(content="x", source=CLEAN_SOURCE)


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [
        (1.0000000001, 1.0),
        (-1e-12, 0.0),
        (0.0, 0.0),
        (1.0, 1.0),
        (0.5, 0.5),
    ],
)
def test_retrieval_result_clamps_floating_point_drift(raw_score: float, expected: float) -> None:
    result = RetrievalResult(chunk=_make_hit(), score=raw_score)

    assert result.score == expected


@pytest.mark.parametrize("raw_score", [-0.1, 1.1, 2.0, float("nan"), float("inf")])
def test_retrieval_result_rejects_genuinely_out_of_range_scores(
    raw_score: float,
) -> None:
    with pytest.raises(ValueError, match="normalized between 0.0 and 1.0"):
        RetrievalResult(chunk=_make_hit(), score=raw_score)


def _make_document(sections: dict[str, str]) -> SupportHelpDocument:
    metadata = SupportHelpMetadata(
        doc_id="support.account",
        title="Account help",
        category="account",
        status="published",
        visibility="public",
        tags=("account",),
        updated_at="2026-06-01",
        reviewed_at="2026-06-01",
    )
    return SupportHelpDocument(
        metadata=metadata,
        body="body",
        source_path="docs/help/support/account.md",
        sections=sections,
    )


def test_support_help_document_sections_survives_asdict() -> None:
    document = _make_document({"Intro": "hello"})

    snapshot = dataclasses.asdict(document)

    assert snapshot["sections"] == {"Intro": "hello"}
    assert isinstance(document.sections, dict)


def test_support_help_document_sections_is_isolated_from_caller_dict() -> None:
    caller_sections = {"Intro": "hello"}
    document = _make_document(caller_sections)

    caller_sections["Intro"] = "mutated"

    assert document.sections == {"Intro": "hello"}


def test_format_chat_chunk_source_accepts_max_index() -> None:
    source = format_chat_chunk_source("support.account", CHAT_CHUNK_MAX_INDEX)

    assert source == f"support.account#chunk-{CHAT_CHUNK_MAX_INDEX}"


@pytest.mark.parametrize("chunk_index", [10000, 99999])
def test_format_chat_chunk_source_rejects_index_above_max_with_clear_message(
    chunk_index: int,
) -> None:
    with pytest.raises(ValueError, match="chunk_index must be at most 9999"):
        format_chat_chunk_source("support.account", chunk_index)


@pytest.mark.parametrize("chunk_index", [0, -1])
def test_format_chat_chunk_source_rejects_non_positive_index(chunk_index: int) -> None:
    with pytest.raises(ValueError, match="chunk_index must be positive"):
        format_chat_chunk_source("support.account", chunk_index)


def test_validate_embedding_vector_normalizes_numeric_values() -> None:
    vector = validate_embedding_vector([0] * CHAT_CHUNK_EMBEDDING_DIMENSIONS)

    assert vector == (0.0,) * CHAT_CHUNK_EMBEDDING_DIMENSIONS
    assert all(isinstance(value, float) for value in vector)


def test_validate_embedding_vector_rejects_wrong_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        validate_embedding_vector([0.0, 1.0])


def test_validate_embedding_vector_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="numeric"):
        validate_embedding_vector(["x"] * CHAT_CHUNK_EMBEDDING_DIMENSIONS)  # type: ignore[list-item]


def test_validate_embedding_vector_rejects_non_finite_values() -> None:
    vector = [0.0] * CHAT_CHUNK_EMBEDDING_DIMENSIONS
    vector[0] = float("inf")

    with pytest.raises(ValueError, match="finite"):
        validate_embedding_vector(vector)


def test_chat_chunk_record_rejects_wrong_dimension_vector() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        ChatChunkRecord(
            id=1,
            content="x",
            embedding_vector=(0.0,),
            source=CLEAN_SOURCE,
            created_at=CREATED_AT,
        )


def test_support_rag_settings_match_team_pinned_mvp_values() -> None:
    """요구사항 변경표(2026-05-29)가 고정한 REQ-CS-007 MVP 설정 회귀 테스트."""
    assert SUPPORT_RAG_SETTINGS.embedding_model == "text-embedding-3-small"
    assert SUPPORT_RAG_SETTINGS.embedding_dimensions == CHAT_CHUNK_EMBEDDING_DIMENSIONS
    assert SUPPORT_RAG_SETTINGS.chunk_size == 1000
    assert SUPPORT_RAG_SETTINGS.chunk_overlap == 150
    assert SUPPORT_RAG_SETTINGS.top_k == 3
    assert SUPPORT_RAG_SETTINGS.score_threshold == 0.37
    assert SUPPORT_RAG_SETTINGS.max_cosine_distance == pytest.approx(0.63)


def test_retrieval_result_meets_threshold_uses_pinned_default() -> None:
    assert RetrievalResult(chunk=_make_hit(), score=0.37).meets_threshold()
    assert not RetrievalResult(chunk=_make_hit(), score=0.369).meets_threshold()
    assert RetrievalResult(chunk=_make_hit(), score=0.2).meets_threshold(threshold=0.1)


def test_chat_chunk_hit_rejects_citation_for_different_source() -> None:
    citation = CitationMetadata(
        source="support.account#chunk-0002",
        doc_id="support.account",
        title="Account help",
        category="account",
        source_path="docs/help/support/account.md",
        section="Intro",
    )

    with pytest.raises(ValueError, match="citation source must match"):
        ChatChunkHit(content="x", source=CLEAN_SOURCE, citation=citation)
