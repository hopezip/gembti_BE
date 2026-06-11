from __future__ import annotations

import secrets
from typing import Any, cast

from app.core.config import settings
from app.core.redis import get_redis

STEAM_SIGNUP_PREFIX = "auth:steam_signup"


def steam_signup_key(signup_token: str) -> str:
    return f"{STEAM_SIGNUP_PREFIX}:{signup_token}"


async def create_steam_signup_session(
    steam_id_64: int,
    avatar_url: str | None,
) -> str:
    signup_token = f"steam_signup_{secrets.token_urlsafe(32)}"
    redis = cast("Any", await get_redis())
    await redis.hset(
        steam_signup_key(signup_token),
        mapping={
            "steam_id_64": str(steam_id_64),
            "avatar_url": avatar_url or "",
        },
    )
    await redis.expire(steam_signup_key(signup_token), settings.STEAM_SIGNUP_TOKEN_TTL_SECONDS)
    return signup_token


async def consume_steam_signup_session(signup_token: str) -> tuple[int, str | None] | None:
    redis = cast("Any", await get_redis())
    key = steam_signup_key(signup_token)
    session = await redis.hgetall(key)
    if not session:
        return None

    await redis.delete(key)
    return int(session["steam_id_64"]), session.get("avatar_url") or None
