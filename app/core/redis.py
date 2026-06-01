from typing import Any, cast

from redis.asyncio import Redis, from_url

from app.core.config import settings
from app.core.security import hash_token

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def refresh_token_key(token_hash: str) -> str:
    return f"auth:refresh:{token_hash}"


def user_refresh_tokens_key(user_id: int) -> str:
    return f"auth:user:{user_id}:refresh_tokens"


async def save_refresh_token(user_id: int, refresh_token: str, provider: str) -> str:
    token_hash = hash_token(refresh_token)
    redis = cast("Any", await get_redis())
    ttl = settings.REFRESH_TOKEN_TTL_SECONDS

    await redis.hset(
        refresh_token_key(token_hash),
        mapping={
            "user_id": str(user_id),
            "provider": provider,
        },
    )
    await redis.expire(refresh_token_key(token_hash), ttl)

    user_tokens_key = user_refresh_tokens_key(user_id)
    await redis.sadd(user_tokens_key, token_hash)
    await redis.expire(user_tokens_key, ttl)

    return token_hash


async def validate_refresh_token(refresh_token: str) -> int | None:
    token_hash = hash_token(refresh_token)
    redis = cast("Any", await get_redis())
    user_id = await redis.hget(refresh_token_key(token_hash), "user_id")
    if user_id is None:
        return None
    return int(user_id)


async def delete_refresh_token(refresh_token: str, user_id: int | None = None) -> None:
    token_hash = hash_token(refresh_token)
    redis = cast("Any", await get_redis())
    await redis.delete(refresh_token_key(token_hash))

    if user_id is not None:
        await redis.srem(user_refresh_tokens_key(user_id), token_hash)


async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
    redis = cast("Any", await get_redis())
    user_tokens_key = user_refresh_tokens_key(user_id)
    token_hashes = await redis.smembers(user_tokens_key)

    if token_hashes:
        await redis.delete(*(refresh_token_key(token_hash) for token_hash in token_hashes))

    await redis.delete(user_tokens_key)
