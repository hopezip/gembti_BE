from datetime import UTC, datetime
from typing import Any, cast

from app.core.redis import get_redis
from app.core.security import decode_token

ACCESS_BLACKLIST_PREFIX = "auth:blacklist:access"


def access_blacklist_key(jti: str) -> str:
    return f"{ACCESS_BLACKLIST_PREFIX}:{jti}"


async def blacklist_access_token(access_token: str) -> bool:
    payload = decode_token(access_token)
    if payload.get("type") != "access":
        return False

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not isinstance(jti, str) or not isinstance(exp, int):
        return False

    ttl = exp - int(datetime.now(UTC).timestamp())
    if ttl <= 0:
        return False

    redis = cast("Any", await get_redis())
    await redis.set(access_blacklist_key(jti), "1", ex=ttl)
    return True


async def is_access_token_blacklisted(access_token: str) -> bool:
    payload = decode_token(access_token)
    if payload.get("type") != "access":
        return True

    jti = payload.get("jti")
    if not isinstance(jti, str):
        return True

    redis = cast("Any", await get_redis())
    return bool(await redis.exists(access_blacklist_key(jti)))
