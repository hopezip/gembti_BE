from collections.abc import Iterator
import json
from uuid import UUID

from httpx import AsyncClient
import pytest

from app.chat.cs import service as support_chat_service
from app.core.dependencies import get_current_user_id
from app.core.enums import RedisPurpose
from app.main import app


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires: dict[str, int] = {}
        self.lists: dict[str, list[str]] = {}

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


def _sse_events(body: str) -> list[str]:
    return [line.removeprefix("data: ") for line in body.splitlines() if line.startswith("data: ")]


def _parsed_sse_events(body: str) -> list[dict[str, object]]:
    return [json.loads(event) for event in _sse_events(body) if event != "[DONE]"]


def _final_sse_event(body: str) -> dict[str, object]:
    final_events = [event for event in _parsed_sse_events(body) if event["type"] == "final"]
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


@pytest.fixture(autouse=True)
def authenticated_user() -> Iterator[None]:
    async def fake_get_current_user_id() -> int:
        return 1

    app.dependency_overrides[get_current_user_id] = fake_get_current_user_id
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


@pytest.mark.asyncio
async def test_support_chat_messages_requires_authentication(
    anon_client: AsyncClient,
) -> None:
    app.dependency_overrides.pop(get_current_user_id, None)

    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": "test message"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "인증이 필요합니다."}


@pytest.mark.asyncio
async def test_support_chat_messages_rejects_blank_message(
    anon_client: AsyncClient,
) -> None:
    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": " "},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "메시지는 필수입니다."}


@pytest.mark.asyncio
async def test_support_chat_messages_rejects_blank_session_id(
    anon_client: AsyncClient,
) -> None:
    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": "test message", "session_id": " "},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "session_id 형식이 올바르지 않습니다."}


def test_support_chat_messages_openapi_success_response_is_sse_only() -> None:
    operation = app.openapi()["paths"]["/api/v1/support/chat/messages"]["post"]
    success_content = operation["responses"]["200"]["content"]

    assert list(success_content) == ["text/event-stream"]


@pytest.mark.asyncio
async def test_support_chat_messages_streams_sse_events_without_accept_header(
    anon_client: AsyncClient,
    fake_redis: FakeRedis,
) -> None:
    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": "test message"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    delta_index = body.index('"type": "delta"')
    final_index = body.index('"type": "final"')
    done_index = body.index("data: [DONE]")

    assert delta_index < final_index < done_index


@pytest.mark.asyncio
async def test_support_chat_messages_streams_sse_events(
    anon_client: AsyncClient,
    fake_redis: FakeRedis,
) -> None:
    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        headers={"accept": "text/event-stream"},
        json={"message": "test message"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text

    delta_index = body.index('"type": "delta"')
    final_index = body.index('"type": "final"')
    done_index = body.index("data: [DONE]")

    assert delta_index < final_index < done_index


@pytest.mark.asyncio
async def test_support_chat_messages_reuses_session_id(
    anon_client: AsyncClient,
    fake_redis: FakeRedis,
) -> None:
    existing_session_id = "existing-session-id"
    key = support_chat_service.support_chat_session_key(existing_session_id)
    fake_redis.hashes[key] = {"turn_count": "1"}

    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": "test message", "session_id": "existing-session-id"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _final_sse_event(response.text)["session_id"] == "existing-session-id"


@pytest.mark.asyncio
async def test_support_chat_messages_recreates_session_when_session_id_expired(
    anon_client: AsyncClient,
    fake_redis: FakeRedis,
) -> None:
    expired_session_id = "expired-session-id"

    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": "test message", "session_id": expired_session_id},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    final_event = _final_sse_event(response.text)
    assert final_event["session_id"] != expired_session_id
    UUID(str(final_event["session_id"]))
    assert final_event["session_expired"] is True
    assert (
        support_chat_service.support_chat_session_key(str(final_event["session_id"]))
        in fake_redis.hashes
    )


@pytest.mark.asyncio
async def test_support_chat_messages_streams_each_answer_delta_before_final(
    anon_client: AsyncClient,
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stream_answer(message: str, recent_turns: list[dict[str, str]]):
        assert message == "test message"
        assert recent_turns == []
        yield support_chat_service.SupportRagAnswerDelta(content="first")
        yield support_chat_service.SupportRagAnswerDelta(content="second")
        yield support_chat_service.SupportRagAnswerFinal(
            answer=support_chat_service.SupportRagAnswer(
                answer="firstsecond",
                citations=[],
                fallback_used=False,
            )
        )

    monkeypatch.setattr(
        support_chat_service,
        "stream_support_chat_answer",
        fake_stream_answer,
    )
    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        headers={"accept": "text/event-stream"},
        json={"message": "test message"},
    )

    events = _sse_events(response.text)
    parsed_events = _parsed_sse_events(response.text)

    delta_events = [event for event in parsed_events if event["type"] == "delta"]
    final_events = [event for event in parsed_events if event["type"] == "final"]

    assert len(delta_events) == 2
    assert [event["content"] for event in delta_events] == ["first", "second"]
    assert len(final_events) == 1
    assert final_events[0]["answer"] == "firstsecond"
    assert parsed_events[-1]["type"] == "final"
    assert events[-1] == "[DONE]"
