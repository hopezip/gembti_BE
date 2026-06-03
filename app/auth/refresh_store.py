from typing import Any, cast

from app.core.config import settings
from app.core.redis import get_redis
from app.core.security import hash_token

REFRESH_PREFIX = "auth:refresh"
USER_REFRESH_PREFIX = "auth:user"


def refresh_key(token_hash: str) -> str:
    return f"{REFRESH_PREFIX}:{token_hash}"


def user_refresh_set_key(user_id: int) -> str:
    return f"{USER_REFRESH_PREFIX}:{user_id}:refresh_tokens"


async def save_refresh_token(user_id: int, refresh_token: str, provider: str) -> str:
    token_hash = hash_token(refresh_token)
    redis = cast("Any", await get_redis())
    ttl = settings.REFRESH_TOKEN_TTL_SECONDS

    await redis.hset(
        refresh_key(token_hash),
        mapping={
            "user_id": str(user_id),
            "provider": provider,
        },
    )
    await redis.expire(refresh_key(token_hash), ttl)

    user_key = user_refresh_set_key(user_id)
    await redis.sadd(user_key, token_hash)
    await redis.expire(user_key, ttl)

    return token_hash


async def validate_refresh_token(refresh_token: str) -> int | None:
    token_hash = hash_token(refresh_token)
    redis = cast("Any", await get_redis())
    user_id = await redis.hget(refresh_key(token_hash), "user_id")
    if user_id is None:
        return None
    return int(user_id)


async def delete_refresh_token(refresh_token: str, user_id: int | None = None) -> None:
    token_hash = hash_token(refresh_token)
    redis = cast("Any", await get_redis())
    await redis.delete(refresh_key(token_hash))

    if user_id is not None:
        await redis.srem(user_refresh_set_key(user_id), token_hash)


async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
    redis = cast("Any", await get_redis())
    user_key = user_refresh_set_key(user_id)
    token_hashes = await redis.smembers(user_key)

    if token_hashes:
        await redis.delete(*(refresh_key(token_hash) for token_hash in token_hashes))

    await redis.delete(user_key)
