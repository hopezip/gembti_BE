from collections.abc import Iterator

import pytest

from app.auth import email_verification_store
from app.auth.models import EmailVerificationPurpose
from app.core.config import settings

PURPOSE = EmailVerificationPurpose.SIGNUP


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int) -> bool:
        self.values[key] = value
        self.expires[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def delete(self, *keys: str) -> int:
        for key in keys:
            self.values.pop(key, None)
        return len(keys)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()

    async def get_fake_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(email_verification_store, "get_redis", get_fake_redis)
    yield redis


def test_email_keys_are_normalized() -> None:
    assert (
        email_verification_store.code_key(" Test@Example.COM ", PURPOSE)
        == "auth:email:code:SIGNUP:test@example.com"
    )


@pytest.mark.asyncio
async def test_save_verification_code_stores_hash(fake_redis: FakeRedis) -> None:
    await email_verification_store.save_verification_code("test@example.com", PURPOSE, "123456")

    key = email_verification_store.code_key("test@example.com", PURPOSE)
    assert fake_redis.values[key] != "123456"
    assert fake_redis.expires[key] == settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS


@pytest.mark.asyncio
async def test_verify_and_consume_email(fake_redis: FakeRedis) -> None:
    email = "test@example.com"
    await email_verification_store.save_verification_code(email, PURPOSE, "123456")

    assert await email_verification_store.verify_email_code(email, PURPOSE, "123456") is True
    assert email_verification_store.code_key(email, PURPOSE) not in fake_redis.values
    assert await email_verification_store.consume_verified_email(email, PURPOSE) is True
    assert await email_verification_store.consume_verified_email(email, PURPOSE) is False


@pytest.mark.asyncio
async def test_wrong_verification_code_is_rejected(fake_redis: FakeRedis) -> None:
    email = "test@example.com"
    await email_verification_store.save_verification_code(email, PURPOSE, "123456")

    assert await email_verification_store.verify_email_code(email, PURPOSE, "000000") is False
