import pytest

from app.chat.infrastructure.embedding import FakeEmbeddingClient
from app.chat.infrastructure.llm import FALLBACK_ANSWER, DeterministicSupportResponder
from app.chat.infrastructure.vector_store import ChatChunkVectorWrite, FakeChatChunkVectorStore
from app.chat.rag.chunking import (
    chat_chunk_drafts_from_chunks,
    chunk_support_help_document,
    load_support_help_documents,
)
from app.chat.rag.service import SupportRagAnswer, SupportRagAnswerFinal, stream_support_rag_answer


async def _collect_final_answer(**kwargs: object) -> SupportRagAnswer:
    async for event in stream_support_rag_answer(**kwargs):  # type: ignore[arg-type]
        if isinstance(event, SupportRagAnswerFinal):
            return event.answer
    raise AssertionError("stream finished without final answer")


class RecordingEmbeddingClient(FakeEmbeddingClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return await super().embed_text(text)


async def _support_docs_store() -> tuple[FakeEmbeddingClient, FakeChatChunkVectorStore]:
    embedder = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore(score_threshold=1.0)
    entries: list[ChatChunkVectorWrite] = []
    for document in load_support_help_documents("docs/help/support"):
        for draft in chat_chunk_drafts_from_chunks(chunk_support_help_document(document)):
            entries.append(
                ChatChunkVectorWrite(
                    content=draft.content,
                    source=draft.source,
                    embedding_vector=tuple(await embedder.embed_text(draft.content)),
                )
            )
    vector_store.upsert(entries)
    return embedder, vector_store


@pytest.mark.asyncio
async def test_fake_store_lexical_recovery_finds_steam_spacing_variant() -> None:
    try:
        from app.chat.rag.query import analyze_support_query
    except ModuleNotFoundError:
        pytest.fail("support query analyzer module is missing")

    embedder = FakeEmbeddingClient()
    vector_store = FakeChatChunkVectorStore(score_threshold=1.0)
    content = "Steam 연동은 선택 단계이며, 연동하지 않아도 설문을 진행할 수 있습니다."
    vector_store.upsert(
        [
            ChatChunkVectorWrite(
                content=content,
                source="support.steam#chunk-0001",
                embedding_vector=tuple(await embedder.embed_text(content)),
            )
        ]
    )

    results = vector_store.search_lexical(analyze_support_query("스팀연동"), top_k=3)

    assert [result.chunk.source for result in results] == ["support.steam#chunk-0001"]
    assert results[0].score >= 0.7


@pytest.mark.asyncio
async def test_stream_support_rag_answer_uses_temporary_lexical_recovery_when_dense_is_empty() -> (
    None
):
    embedder = RecordingEmbeddingClient()
    vector_store = FakeChatChunkVectorStore(score_threshold=1.0)
    responder = DeterministicSupportResponder()
    content = "Steam 연동은 선택 단계이며, 연동하지 않아도 설문을 진행할 수 있습니다."
    vector_store.upsert(
        [
            ChatChunkVectorWrite(
                content=content,
                source="support.steam#chunk-0001",
                embedding_vector=tuple(await embedder.embed_text(content)),
            )
        ]
    )
    embedder.calls.clear()

    result = await _collect_final_answer(
        message="스팀연동",
        embedding_client=embedder,
        vector_store=vector_store,
        responder=responder,
    )

    assert result.fallback_used is False
    assert content in result.answer
    assert "스팀연동" in embedder.calls


@pytest.mark.asyncio
async def test_stream_support_rag_answer_skips_embedding_for_programming_library_negative() -> None:
    embedder = RecordingEmbeddingClient()
    vector_store = FakeChatChunkVectorStore()
    responder = DeterministicSupportResponder()

    result = await _collect_final_answer(
        message="파이썬 라이브러리 추천해줘",
        embedding_client=embedder,
        vector_store=vector_store,
        responder=responder,
    )

    assert result.answer == FALLBACK_ANSWER
    assert result.fallback_used is True
    assert embedder.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "회원가입",
        "성향 스탯이 없다고 나와요",
        "내 취향에 맞는 게임 하나 바로 골라줘",
        "게임은 어디서 검색하나요?",
        "친구랑 같이 할 게임만 보고 싶어요",
        "세션",
        "안 떠요",
    ],
)
async def test_support_docs_lexical_recovery_covers_eval_set_support_misses(
    query: str,
) -> None:
    embedder, vector_store = await _support_docs_store()

    results = await _collect_final_answer(
        message=query,
        embedding_client=embedder,
        vector_store=vector_store,
        responder=DeterministicSupportResponder(),
    )

    assert results.fallback_used is False
