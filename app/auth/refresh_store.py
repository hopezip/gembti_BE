from typing import Any, cast

from jose import JWTError

from app.core.config import settings
from app.core.enums import RedisPurpose
from app.core.redis import get_redis
from app.core.security import decode_token

REFRESH_PREFIX = "auth:refresh"
USER_REFRESH_PREFIX = "auth:user"


def refresh_key(jti: str) -> str:
    return f"{REFRESH_PREFIX}:{jti}"


def user_refresh_set_key(user_id: int) -> str:
    return f"{USER_REFRESH_PREFIX}:{user_id}:refresh_tokens"


async def save_refresh_token(user_id: int, refresh_token: str, provider: str) -> str:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("Refresh Token이 아닙니다.")

    jti = payload.get("jti")
    subject = payload.get("sub")
    if not isinstance(jti, str) or subject != str(user_id):
        raise ValueError("Refresh Token 정보가 올바르지 않습니다.")

    redis = cast("Any", await get_redis(RedisPurpose.AUTH))
    ttl = settings.REFRESH_TOKEN_TTL_SECONDS

    await redis.hset(
        refresh_key(jti),
        mapping={
            "user_id": str(user_id),
            "provider": provider,
        },
    )
    await redis.expire(refresh_key(jti), ttl)

    user_key = user_refresh_set_key(user_id)
    await redis.sadd(user_key, jti)
    await redis.expire(user_key, ttl)

    return jti


async def validate_refresh_token(refresh_token: str) -> int | None:
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        return None

    if payload.get("type") != "refresh":
        return None

    jti = payload.get("jti")
    subject = payload.get("sub")
    if not isinstance(jti, str) or not isinstance(subject, str):
        return None

    redis = cast("Any", await get_redis(RedisPurpose.AUTH))
    user_id = await redis.hget(refresh_key(jti), "user_id")
    if user_id is None or user_id != subject:
        return None
    return int(user_id)


async def delete_refresh_token(refresh_token: str, user_id: int | None = None) -> None:
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        return

    jti = payload.get("jti")
    if not isinstance(jti, str):
        return

    redis = cast("Any", await get_redis(RedisPurpose.AUTH))
    await redis.delete(refresh_key(jti))

    if user_id is not None:
        await redis.srem(user_refresh_set_key(user_id), jti)


async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
    redis = cast("Any", await get_redis(RedisPurpose.AUTH))
    user_key = user_refresh_set_key(user_id)
    token_jtis = await redis.smembers(user_key)

    if token_jtis:
        await redis.delete(*(refresh_key(jti) for jti in token_jtis))

    await redis.delete(user_key)
