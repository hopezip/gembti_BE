import pytest

from app.chat.infrastructure.embedding import FakeEmbeddingClient
from app.chat.infrastructure.llm import FALLBACK_ANSWER, DeterministicSupportResponder
from app.chat.infrastructure.vector_store import (
    ChatChunkVectorWrite,
    FakeChatChunkVectorStore,
)
from app.chat.rag.service import SupportRagAnswer, SupportRagAnswerFinal, stream_support_rag_answer


async def collect_final_answer(**kwargs: object) -> SupportRagAnswer:
    async for event in stream_support_rag_answer(**kwargs):  # type: ignore[arg-type]
        if isinstance(event, SupportRagAnswerFinal):
            return event.answer
    raise AssertionError("stream finished without final answer")


class RecordingSupportResponder:
    def __init__(self) -> None:
        self.received_recent_turns = None

    async def stream_answer(self, question, chunks, recent_turns=None):
        self.received_recent_turns = recent_turns
        yield "generated answer"


class RecordingEmbeddingClient(FakeEmbeddingClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return await super().embed_text(text)


@pytest.mark.asyncio
async def test_stream_support_rag_answer_passes_recent_turns_to_responder() -> None:
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = RecordingSupportResponder()
    recent_turns = [{"user": "old question", "assistant": "old answer"}]

    result = await collect_final_answer(
        message="new question",
        recent_turns=recent_turns,
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )

    assert result.answer == "generated answer"
    assert responder.received_recent_turns == recent_turns


@pytest.mark.asyncio
async def test_stream_support_rag_answer_embeds_current_message_only() -> None:
    embedding_client = RecordingEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = RecordingSupportResponder()
    recent_turns = [
        {
            "user": "old password reset question",
            "assistant": "old password reset answer",
        }
    ]

    await collect_final_answer(
        message="new steam sync question",
        recent_turns=recent_turns,
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )

    assert embedding_client.calls == ["new steam sync question"]


@pytest.mark.asyncio
async def test_stream_support_rag_answer_awaits_embedding_client() -> None:
    embedding_client = RecordingEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = RecordingSupportResponder()

    await collect_final_answer(
        message="new async embedding question",
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )

    assert embedding_client.calls == ["new async embedding question"]


@pytest.mark.asyncio
async def test_stream_support_rag_answer_uses_retrieved_chunks() -> None:
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = DeterministicSupportResponder()

    chunk_content = "Password reset is available from the account settings page."

    vector_store.upsert(
        [
            ChatChunkVectorWrite(
                content=chunk_content,
                source="support.account#chunk-0001",
                embedding_vector=tuple(await embedding_client.embed_text(chunk_content)),
            )
        ]
    )

    result = await collect_final_answer(
        message="How do I reset my password?",
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )

    assert chunk_content in result.answer
    assert result.citations == []
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_stream_support_rag_answer_returns_fallback_when_no_chunks() -> None:
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = DeterministicSupportResponder()

    result = await collect_final_answer(
        message="How do I reset my password?",
        embedding_client=embedding_client,
        vector_store=vector_store,
        responder=responder,
    )
    assert result.answer == FALLBACK_ANSWER
    assert result.citations == []
    assert result.fallback_used is True
