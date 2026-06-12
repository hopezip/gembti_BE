from collections.abc import Iterator
import json
from uuid import UUID

import pytest

from app.chat.cs import service as support_chat_service
from app.chat.schemas import SupportChatMessageRequest
from app.core.config import settings


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


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()

    async def get_fake_redis() -> FakeRedis:
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
async def test_create_support_chat_message_creates_redis_session_when_session_id_missing(
    fake_redis: FakeRedis,
) -> None:
    request = SupportChatMessageRequest(message="test message")

    response = await support_chat_service.create_support_chat_message(request)

    key = support_chat_service.support_chat_session_key(response.session_id)
    assert key in fake_redis.hashes
    assert fake_redis.hashes[key] == {"turn_count": "0"}
    assert response.session_expired is False


@pytest.mark.asyncio
async def test_create_support_chat_message_saves_turn_after_response(
    fake_redis: FakeRedis,
) -> None:
    request = SupportChatMessageRequest(message="hello")

    response = await support_chat_service.create_support_chat_message(request)

    turns_key = support_chat_service.support_chat_session_turns_key(response.session_id)
    saved_turn = json.loads(fake_redis.lists[turns_key][0])
    assert saved_turn == {"user": "hello", "assistant": response.answer}


@pytest.mark.asyncio
async def test_create_support_chat_message_reuses_existing_redis_session_and_refreshes_ttl(
    fake_redis: FakeRedis,
) -> None:
    existing_session_id = "existing-session-id"
    key = support_chat_service.support_chat_session_key(existing_session_id)
    fake_redis.hashes[key] = {"turn_count": "1"}

    request = SupportChatMessageRequest(
        message="next message",
        session_id=existing_session_id,
    )

    response = await support_chat_service.create_support_chat_message(request)

    assert response.session_id == existing_session_id
    assert response.session_expired is False
    assert fake_redis.expires[key] == settings.SUPPORT_CHAT_SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_create_support_chat_message_recreates_session_when_existing_session_expired(
    fake_redis: FakeRedis,
) -> None:
    expired_session_id = "expired-session-id"
    request = SupportChatMessageRequest(
        message="next message",
        session_id=expired_session_id,
    )

    response = await support_chat_service.create_support_chat_message(request)

    new_key = support_chat_service.support_chat_session_key(response.session_id)
    assert response.session_id != expired_session_id
    UUID(response.session_id)
    assert response.session_expired is True
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
async def test_create_support_chat_message_passes_recent_turns_to_answer_generator(
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

    captured = {}

    async def fake_generate_answer(message: str, recent_turns: list[dict[str, str]]) -> str:
        captured["message"] = message
        captured["recent_turns"] = recent_turns
        return "generated answer"

    monkeypatch.setattr(
        support_chat_service,
        "generate_support_chat_answer",
        fake_generate_answer,
    )

    request = SupportChatMessageRequest(
        message="new question",
        session_id=existing_session_id,
    )

    response = await support_chat_service.create_support_chat_message(request)

    assert response.answer == "generated answer"
    assert captured["message"] == "new question"
    assert captured["recent_turns"] == [
        {"user": "hello-1", "assistant": "hi-1"},
        {"user": "hello-2", "assistant": "hi-2"},
    ]


@pytest.mark.asyncio
async def test_create_support_chat_message_uses_empty_recent_turns_when_session_expired(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired_session_id = "expired-session-id"
    captured = {}

    async def fake_generate_answer(
        message: str,
        recent_turns: list[dict[str, str]],
    ) -> str:
        captured["message"] = message
        captured["recent_turns"] = recent_turns
        return "generated answer"

    monkeypatch.setattr(
        support_chat_service,
        "generate_support_chat_answer",
        fake_generate_answer,
    )

    request = SupportChatMessageRequest(
        message="new question",
        session_id=expired_session_id,
    )

    response = await support_chat_service.create_support_chat_message(request)

    assert response.answer == "generated answer"
    assert response.session_expired is True
    assert response.session_id != expired_session_id
    assert captured["message"] == "new question"
    assert captured["recent_turns"] == []
