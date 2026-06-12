from collections.abc import Iterator
from uuid import UUID

from httpx import AsyncClient
import pytest

from app.chat.cs import service as support_chat_service
from app.core.dependencies import get_current_user_id
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


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()

    async def get_fake_redis() -> FakeRedis:
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


@pytest.mark.asyncio
async def test_support_chat_messages_returns_answer_payload(
    anon_client: AsyncClient,
    fake_redis: FakeRedis,
) -> None:
    response = await anon_client.post(
        "/api/v1/support/chat/messages",
        json={"message": "test message"},
    )

    assert response.status_code == 200
    response_json = response.json()
    assert "answer" in response_json
    assert "citations" in response_json
    assert "fallback_used" in response_json
    assert "session_expired" in response_json
    assert isinstance(response_json["answer"], str)
    assert isinstance(response_json["citations"], list)
    assert isinstance(response_json["fallback_used"], bool)
    assert isinstance(response_json["session_expired"], bool)
    assert "suggested_next_steps" not in response_json
    assert response_json["session_id"] != "temporary-session-id"
    UUID(response_json["session_id"])


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
    assert response.json()["session_id"] == "existing-session-id"


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
    response_json = response.json()
    assert response_json["session_id"] != expired_session_id
    UUID(response_json["session_id"])
    assert response_json["session_expired"] is True
    assert (
        support_chat_service.support_chat_session_key(response_json["session_id"])
        in fake_redis.hashes
    )
