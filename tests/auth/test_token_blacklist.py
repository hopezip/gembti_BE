from collections.abc import Iterator

from jose import jwt
import pytest

from app.auth import token_blacklist
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int) -> bool:
        self.values[key] = value
        self.expires[key] = ex
        return True

    async def exists(self, key: str) -> int:
        return int(key in self.values)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()

    async def get_fake_redis(purpose: object | None = None) -> FakeRedis:
        return redis

    monkeypatch.setattr(token_blacklist, "get_redis", get_fake_redis)
    yield redis


def test_access_blacklist_key() -> None:
    assert token_blacklist.access_blacklist_key("abc") == "auth:blacklist:access:abc"


@pytest.mark.asyncio
async def test_blacklist_access_token(fake_redis: FakeRedis) -> None:
    token = create_access_token(subject=7)
    payload = decode_token(token)

    assert await token_blacklist.blacklist_access_token(token) is True
    key = token_blacklist.access_blacklist_key(payload["jti"])
    assert fake_redis.values[key] == "1"
    assert fake_redis.expires[key] > 0
    assert await token_blacklist.is_access_token_blacklisted(token) is True


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_access_blacklisted(fake_redis: FakeRedis) -> None:
    token = create_refresh_token(subject=7)

    assert await token_blacklist.blacklist_access_token(token) is False
    assert await token_blacklist.is_access_token_blacklisted(token) is True


@pytest.mark.asyncio
async def test_invalid_token_is_rejected_without_redis_lookup(fake_redis: FakeRedis) -> None:
    token = "invalid.token"

    assert await token_blacklist.blacklist_access_token(token) is False
    assert await token_blacklist.is_access_token_blacklisted(token) is True
    assert fake_redis.values == {}


@pytest.mark.asyncio
async def test_access_token_without_required_claims_is_rejected(fake_redis: FakeRedis) -> None:
    token = jwt.encode(
        {"sub": "7", "type": "access"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert await token_blacklist.blacklist_access_token(token) is False
    assert await token_blacklist.is_access_token_blacklisted(token) is True
    assert fake_redis.values == {}
