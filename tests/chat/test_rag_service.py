import pytest

from app.chat.infrastructure.embedding import FakeEmbeddingClient
from app.chat.infrastructure.llm import FALLBACK_ANSWER, DeterministicSupportResponder
from app.chat.infrastructure.vector_store import (
    ChatChunkVectorWrite,
    FakeChatChunkVectorStore,
)
from app.chat.rag.service import generate_support_rag_answer


@pytest.mark.asyncio
async def test_generate_support_rag_answer_uses_retrieved_chunks() -> None:
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = DeterministicSupportResponder()

    chunk_content = "Password reset is available from the account settings page."

    vector_store.upsert(
        [
            ChatChunkVectorWrite(
                content=chunk_content,
                source="support.account#chunk-0001",
                embedding_vector=tuple(embedding_client.embed_text(chunk_content)),
            )
        ]
    )

    result = await generate_support_rag_answer(
        message="How do I reset my password?",
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )

    assert chunk_content in result.answer
    assert result.citations == []
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_generate_support_rag_answer_returns_fallback_when_no_chunks() -> None:
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = DeterministicSupportResponder()

    result = await generate_support_rag_answer(
        message="How do I reset my password?",
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )
    assert result.answer == FALLBACK_ANSWER
    assert result.citations == []
    assert result.fallback_used is True
