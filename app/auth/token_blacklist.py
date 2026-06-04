from datetime import UTC, datetime
from typing import Any, cast

from jose import JWTError

from app.core.redis import get_redis
from app.core.security import TokenPayload, decode_token

ACCESS_BLACKLIST_PREFIX = "auth:blacklist:access"


def access_blacklist_key(jti: str) -> str:
    return f"{ACCESS_BLACKLIST_PREFIX}:{jti}"


def decode_valid_access_token(access_token: str) -> TokenPayload | None:
    try:
        payload = decode_token(access_token)
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    subject = payload.get("sub")
    jti = payload.get("jti")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(jti, str)
        or not jti
        or not isinstance(issued_at, int)
        or not isinstance(expires_at, int)
    ):
        return None

    return payload


async def blacklist_access_token(access_token: str) -> bool:
    payload = decode_valid_access_token(access_token)
    if payload is None:
        return False

    ttl = payload["exp"] - int(datetime.now(UTC).timestamp())
    if ttl <= 0:
        return False

    redis = cast("Any", await get_redis())
    await redis.set(access_blacklist_key(payload["jti"]), "1", ex=ttl)
    return True


async def is_access_token_blacklisted(access_token: str) -> bool:
    payload = decode_valid_access_token(access_token)
    if payload is None:
        return True

    redis = cast("Any", await get_redis())
    return bool(await redis.exists(access_blacklist_key(payload["jti"])))
