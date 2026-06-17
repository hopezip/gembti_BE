from collections.abc import Iterator
import json
from uuid import UUID

import pytest

from app.chat.cs import service as support_chat_service
from app.chat.schemas import SupportChatMessageRequest
from app.core.config import settings
from app.core.enums import RedisPurpose


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.expires: dict[str, int] = {}

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes[key] = mapping
        return len(mapping)

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True

    async def exists(self, key: str) -> int:
        return int(key in self.hashes)

    async def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        values = self.lists.get(key, [])
        length = len(values)
        if start < 0:
            start = length + start
        if stop < 0:
            stop = length + stop
        start = max(start, 0)
        stop = min(stop, length - 1)
        self.lists[key] = values[start : stop + 1] if start <= stop else []
        return True

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        values = self.lists.get(key, [])
        if stop == -1:
            return values[start:]
        return values[start : stop + 1]


async def collect_support_chat_events(
    request: SupportChatMessageRequest,
) -> list[dict[str, object]]:
    return [event async for event in support_chat_service.stream_support_chat_message(request)]


def final_support_chat_event(events: list[dict[str, object]]) -> dict[str, object]:
    final_events = [event for event in events if event["type"] == "final"]
    assert len(final_events) == 1
    return final_events[0]


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()

    async def get_fake_redis(purpose: RedisPurpose) -> FakeRedis:
        assert purpose == RedisPurpose.SUPPORT
        return redis

    monkeypatch.setattr(support_chat_service, "get_redis", get_fake_redis)
    yield redis


def test_support_chat_session_key() -> None:
    assert support_chat_service.support_chat_session_key("abc") == "support_chat:session:abc"


def test_support_chat_session_turns_key() -> None:
    assert (
        support_chat_service.support_chat_session_turns_key("abc")
        == "support_chat:session:abc:turns"
    )


@pytest.mark.asyncio
async def test_create_support_chat_session_stores_session_with_ttl(
    fake_redis: FakeRedis,
) -> None:
    session_id = await support_chat_service.create_support_chat_session()

    UUID(session_id)
    key = support_chat_service.support_chat_session_key(session_id)

    assert fake_redis.hashes[key] == {"turn_count": "0"}
    assert fake_redis.expires[key] == settings.SUPPORT_CHAT_SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_stream_support_chat_message_creates_redis_session_when_session_id_missing(
    fake_redis: FakeRedis,
) -> None:
    request = SupportChatMessageRequest(message="test message")

    final_event = final_support_chat_event(await collect_support_chat_events(request))

    key = support_chat_service.support_chat_session_key(str(final_event["session_id"]))
    assert key in fake_redis.hashes
    assert fake_redis.hashes[key] == {"turn_count": "0"}
    assert final_event["session_expired"] is False


@pytest.mark.asyncio
async def test_stream_support_chat_message_saves_turn_after_final_event(
    fake_redis: FakeRedis,
) -> None:
    request = SupportChatMessageRequest(message="hello")

    final_event = final_support_chat_event(await collect_support_chat_events(request))

    turns_key = support_chat_service.support_chat_session_turns_key(str(final_event["session_id"]))
    saved_turn = json.loads(fake_redis.lists[turns_key][0])
    assert saved_turn == {"user": "hello", "assistant": final_event["answer"]}


@pytest.mark.asyncio
async def test_stream_support_chat_message_reuses_existing_redis_session_and_refreshes_ttl(
    fake_redis: FakeRedis,
) -> None:
    existing_session_id = "existing-session-id"
    key = support_chat_service.support_chat_session_key(existing_session_id)
    fake_redis.hashes[key] = {"turn_count": "1"}

    request = SupportChatMessageRequest(
        message="next message",
        session_id=existing_session_id,
    )

    final_event = final_support_chat_event(await collect_support_chat_events(request))

    assert final_event["session_id"] == existing_session_id
    assert final_event["session_expired"] is False
    assert fake_redis.expires[key] == settings.SUPPORT_CHAT_SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_stream_support_chat_message_recreates_session_when_existing_session_expired(
    fake_redis: FakeRedis,
) -> None:
    expired_session_id = "expired-session-id"
    request = SupportChatMessageRequest(
        message="next message",
        session_id=expired_session_id,
    )

    final_event = final_support_chat_event(await collect_support_chat_events(request))

    new_session_id = str(final_event["session_id"])
    new_key = support_chat_service.support_chat_session_key(new_session_id)
    assert new_session_id != expired_session_id
    UUID(new_session_id)
    assert final_event["session_expired"] is True
    assert new_key in fake_redis.hashes
    assert fake_redis.expires[new_key] == settings.SUPPORT_CHAT_SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_save_support_chat_turn_stores_turn_and_keeps_ttl(
    fake_redis: FakeRedis,
) -> None:
    session_id = "session-1"

    await support_chat_service.save_support_chat_turn(
        session_id=session_id,
        user_message="hello",
        assistant_answer="hi",
    )

    turns_key = support_chat_service.support_chat_session_turns_key(session_id)
    saved_turn = json.loads(fake_redis.lists[turns_key][0])
    assert saved_turn == {"user": "hello", "assistant": "hi"}
    assert fake_redis.expires[turns_key] == settings.SUPPORT_CHAT_SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_save_support_chat_turn_keeps_only_recent_three_turns(
    fake_redis: FakeRedis,
) -> None:
    session_id = "session-1"
    turns_key = support_chat_service.support_chat_session_turns_key(session_id)

    for i in range(4):
        await support_chat_service.save_support_chat_turn(
            session_id=session_id,
            user_message=f"hello-{i}",
            assistant_answer=f"hi-{i}",
        )

    assert [json.loads(turn) for turn in fake_redis.lists[turns_key]] == [
        {"user": "hello-1", "assistant": "hi-1"},
        {"user": "hello-2", "assistant": "hi-2"},
        {"user": "hello-3", "assistant": "hi-3"},
    ]


@pytest.mark.asyncio
async def test_get_recent_support_chat_turns_returns_saved_turns(
    fake_redis: FakeRedis,
) -> None:
    session_id = "session-1"

    for i in range(1, 3):
        await support_chat_service.save_support_chat_turn(
            session_id=session_id,
            user_message=f"hello-{i}",
            assistant_answer=f"hi-{i}",
        )

    turns = await support_chat_service.get_recent_support_chat_turns(session_id)

    assert turns == [
        {"user": "hello-1", "assistant": "hi-1"},
        {"user": "hello-2", "assistant": "hi-2"},
    ]


@pytest.mark.asyncio
async def test_stream_support_chat_answer_passes_current_message_and_recent_turns_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recent_turns = [{"user": "old question", "assistant": "old answer"}]
    captured: dict[str, object] = {}

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    async def fake_stream_support_rag_answer(
        *,
        message: str,
        recent_turns: list[dict[str, str]],
        embedding_client: object,
        vector_store: object,
        responder: object,
    ):
        del embedding_client, vector_store, responder
        captured["message"] = message
        captured["recent_turns"] = recent_turns
        yield support_chat_service.SupportRagAnswerFinal(
            answer=support_chat_service.SupportRagAnswer(
                answer="generated answer",
                citations=[],
                fallback_used=False,
            )
        )

    monkeypatch.setattr(support_chat_service, "AsyncSessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        support_chat_service.OpenAIEmbeddingClient,
        "from_env",
        lambda: object(),
    )
    monkeypatch.setattr(
        support_chat_service,
        "AsyncPgvectorChatChunkVectorStore",
        lambda db, score_threshold: object(),
    )
    monkeypatch.setattr(
        support_chat_service.OpenAIChatResponder,
        "from_env",
        lambda: object(),
    )
    monkeypatch.setattr(
        support_chat_service,
        "stream_support_rag_answer",
        fake_stream_support_rag_answer,
    )

    events = [
        event
        async for event in support_chat_service.stream_support_chat_answer(
            message="new question",
            recent_turns=recent_turns,
        )
    ]
    final_event = events[-1]

    assert isinstance(final_event, support_chat_service.SupportRagAnswerFinal)
    assert final_event.answer.answer == "generated answer"
    assert captured["message"] == "new question"
    assert captured["recent_turns"] == recent_turns


@pytest.mark.asyncio
async def test_stream_support_chat_message_passes_recent_turns_to_answer_generator(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_session_id = "existing-session-id"
    key = support_chat_service.support_chat_session_key(existing_session_id)
    fake_redis.hashes[key] = {"turn_count": "2"}

    await support_chat_service.save_support_chat_turn(
        session_id=existing_session_id,
        user_message="hello-1",
        assistant_answer="hi-1",
    )
    await support_chat_service.save_support_chat_turn(
        session_id=existing_session_id,
        user_message="hello-2",
        assistant_answer="hi-2",
    )

    captured: dict[str, object] = {}

    async def fake_stream_answer(message: str, recent_turns: list[dict[str, str]]):
        captured["message"] = message
        captured["recent_turns"] = recent_turns
        yield support_chat_service.SupportRagAnswerFinal(
            answer=support_chat_service.SupportRagAnswer(
                answer="generated answer",
                citations=[],
                fallback_used=False,
            )
        )

    monkeypatch.setattr(
        support_chat_service,
        "stream_support_chat_answer",
        fake_stream_answer,
    )

    request = SupportChatMessageRequest(
        message="new question",
        session_id=existing_session_id,
    )

    final_event = final_support_chat_event(await collect_support_chat_events(request))

    assert final_event["answer"] == "generated answer"
    assert captured["message"] == "new question"
    assert captured["recent_turns"] == [
        {"user": "hello-1", "assistant": "hi-1"},
        {"user": "hello-2", "assistant": "hi-2"},
    ]


@pytest.mark.asyncio
async def test_stream_support_chat_message_uses_empty_recent_turns_when_session_expired(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired_session_id = "expired-session-id"
    captured: dict[str, object] = {}

    async def fake_stream_answer(
        message: str,
        recent_turns: list[dict[str, str]],
    ):
        captured["message"] = message
        captured["recent_turns"] = recent_turns
        yield support_chat_service.SupportRagAnswerFinal(
            answer=support_chat_service.SupportRagAnswer(
                answer="generated answer",
                citations=[],
                fallback_used=False,
            )
        )

    monkeypatch.setattr(
        support_chat_service,
        "stream_support_chat_answer",
        fake_stream_answer,
    )

    request = SupportChatMessageRequest(
        message="new question",
        session_id=expired_session_id,
    )

    final_event = final_support_chat_event(await collect_support_chat_events(request))

    assert final_event["answer"] == "generated answer"
    assert final_event["session_expired"] is True
    assert final_event["session_id"] != expired_session_id
    assert captured["message"] == "new question"
    assert captured["recent_turns"] == []
