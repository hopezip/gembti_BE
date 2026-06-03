from collections.abc import Iterator

import pytest

from app.auth import refresh_store
from app.core.security import create_refresh_token, hash_token


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.expires: dict[str, int] = {}
        self.deleted: list[str] = []

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes[key] = mapping
        return len(mapping)

    async def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(field)

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True

    async def sadd(self, key: str, value: str) -> int:
        self.sets.setdefault(key, set()).add(value)
        return 1

    async def srem(self, key: str, value: str) -> int:
        self.sets.setdefault(key, set()).discard(value)
        return 1

    async def smembers(self, key: str) -> set[str]:
        return self.sets.get(key, set())

    async def delete(self, *keys: str) -> int:
        for key in keys:
            self.deleted.append(key)
            self.hashes.pop(key, None)
            self.sets.pop(key, None)
        return len(keys)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()

    async def get_fake_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(refresh_store, "get_redis", get_fake_redis)
    yield redis


def test_refresh_key() -> None:
    assert refresh_store.refresh_key("abc") == "auth:refresh:abc"


def test_user_refresh_set_key() -> None:
    assert refresh_store.user_refresh_set_key(7) == "auth:user:7:refresh_tokens"


@pytest.mark.asyncio
async def test_save_refresh_token(fake_redis: FakeRedis) -> None:
    token = create_refresh_token()
    token_hash = await refresh_store.save_refresh_token(7, token, "email")

    refresh_key = refresh_store.refresh_key(token_hash)
    user_key = refresh_store.user_refresh_set_key(7)

    assert token_hash == hash_token(token)
    assert fake_redis.hashes[refresh_key] == {"user_id": "7", "provider": "email"}
    assert token_hash in fake_redis.sets[user_key]
    assert fake_redis.expires[refresh_key] > 0
    assert fake_redis.expires[user_key] > 0


@pytest.mark.asyncio
async def test_validate_refresh_token(fake_redis: FakeRedis) -> None:
    token = create_refresh_token()
    await refresh_store.save_refresh_token(7, token, "email")

    assert await refresh_store.validate_refresh_token(token) == 7


@pytest.mark.asyncio
async def test_validate_missing_refresh_token(fake_redis: FakeRedis) -> None:
    token = create_refresh_token()

    assert await refresh_store.validate_refresh_token(token) is None


@pytest.mark.asyncio
async def test_delete_refresh_token(fake_redis: FakeRedis) -> None:
    token = create_refresh_token()
    token_hash = await refresh_store.save_refresh_token(7, token, "email")

    await refresh_store.delete_refresh_token(token, user_id=7)

    assert refresh_store.refresh_key(token_hash) not in fake_redis.hashes
    assert token_hash not in fake_redis.sets[refresh_store.user_refresh_set_key(7)]


@pytest.mark.asyncio
async def test_delete_all_refresh_tokens_for_user(fake_redis: FakeRedis) -> None:
    first_token = create_refresh_token()
    second_token = create_refresh_token()
    first_hash = await refresh_store.save_refresh_token(7, first_token, "email")
    second_hash = await refresh_store.save_refresh_token(7, second_token, "email")

    await refresh_store.delete_all_refresh_tokens_for_user(7)

    assert refresh_store.refresh_key(first_hash) not in fake_redis.hashes
    assert refresh_store.refresh_key(second_hash) not in fake_redis.hashes
    assert refresh_store.user_refresh_set_key(7) not in fake_redis.sets
