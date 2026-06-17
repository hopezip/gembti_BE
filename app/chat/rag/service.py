"""고객센터 RAG 답변 생성 서비스."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from app.chat.infrastructure.vector_store import ChatChunkVectorWrite
from app.chat.rag.chunking import (
    chat_chunk_drafts_from_chunks,
    chunk_support_help_document,
    load_support_help_documents,
)
from app.chat.rag.model import SUPPORT_RAG_SETTINGS
from app.chat.schemas import SupportChatCitation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.chat.infrastructure.embedding import EmbeddingClient
    from app.chat.infrastructure.llm import SupportResponder
    from app.chat.infrastructure.vector_store import ChatChunkVectorStore
    from app.chat.rag.model import RetrievalResult


@dataclass(frozen=True)
class SupportRagAnswer:
    answer: str
    citations: list[SupportChatCitation]
    fallback_used: bool


@dataclass(frozen=True)
class SupportRagAnswerDelta:
    content: str


@dataclass(frozen=True)
class SupportRagAnswerFinal:
    answer: SupportRagAnswer


@dataclass(frozen=True)
class SupportRagIngestionResult:
    """고객센터 RAG 문서 적재 결과"""

    document_count: int
    chunk_count: int


async def stream_support_rag_answer(
    message: str,
    *,
    recent_turns: list[dict[str, str]] | None = None,
    embedding_client: EmbeddingClient,
    vector_store: ChatChunkVectorStore,
    responder: SupportResponder,
) -> AsyncIterator[SupportRagAnswerDelta | SupportRagAnswerFinal]:
    """질문을 벡터 검색한 뒤, 답변 조각과 최종 결과를 순서대로 흘려보낸다."""
    retrieval_results = await _retrieve_support_rag_chunks(
        message,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    chunks = tuple(result.chunk for result in retrieval_results)

    answer_deltas: list[str] = []
    async for delta in responder.stream_answer(
        message,
        chunks,
        recent_turns=recent_turns,
    ):
        answer_deltas.append(delta)
        yield SupportRagAnswerDelta(content=delta)

    yield SupportRagAnswerFinal(
        answer=SupportRagAnswer(
            answer="".join(answer_deltas),
            citations=_build_citations(retrieval_results),
            fallback_used=not chunks,
        )
    )


async def _retrieve_support_rag_chunks(
    message: str,
    *,
    embedding_client: EmbeddingClient,
    vector_store: ChatChunkVectorStore,
) -> list[RetrievalResult]:
    query_embedding = await embedding_client.embed_text(message)
    raw_retrieval_results = vector_store.search(
        query_embedding,
        top_k=SUPPORT_RAG_SETTINGS.top_k,
    )
    return (
        await raw_retrieval_results
        if inspect.isawaitable(raw_retrieval_results)
        else raw_retrieval_results
    )


async def ingest_support_help_documents(
    *,
    embedding_client: EmbeddingClient,
    vector_store: ChatChunkVectorStore,
    directory: Path | str = Path("docs/help/support"),
) -> SupportRagIngestionResult:
    """고객센터 공개 도움말 Markdown 파일들을 RAG 벡터 저장소에 적재한다."""

    documents = load_support_help_documents(directory)

    drafts = [
        draft
        for document in documents
        for draft in chat_chunk_drafts_from_chunks(
            chunk_support_help_document(document),
        )
    ]

    entries = []
    for draft in drafts:
        entries.append(
            ChatChunkVectorWrite(
                content=draft.content,
                source=draft.source,
                embedding_vector=tuple(await embedding_client.embed_text(draft.content)),
            )
        )

    raw_upsert_result = cast("Any", vector_store.upsert)(entries)
    if inspect.isawaitable(raw_upsert_result):
        await raw_upsert_result

    return SupportRagIngestionResult(
        document_count=len(documents),
        chunk_count=len(entries),
    )


def _build_citations(retrieval_results: list[RetrievalResult]) -> list[SupportChatCitation]:
    citations: list[SupportChatCitation] = []
    for result in retrieval_results:
        chunk = result.chunk
        if chunk.id is None:
            continue
        citations.append(
            SupportChatCitation(
                document_id=chunk.id,
                title=chunk.title,
                chunk_id=chunk.parsed_source.chunk_index,
                similarity=result.score,
            )
        )
    return citations
