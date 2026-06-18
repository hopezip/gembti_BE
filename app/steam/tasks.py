from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.core.database import AsyncSessionLocal
from app.core.enums import RedisPurpose
from app.core.redis import get_redis
from app.steam.service import sync_steam_library

STEAM_LIBRARY_SYNC_COOLDOWN = timedelta(hours=24)
STEAM_LIBRARY_SYNC_LOCK_TTL_SECONDS = 30 * 60


def steam_library_sync_lock_key(user_id: int) -> str:
    return f"steam:library_sync:{user_id}:lock"


def is_steam_library_sync_due(
    last_synced_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    if last_synced_at is None:
        return True

    current_time = now or datetime.now(UTC)
    if last_synced_at.tzinfo is None:
        last_synced_at = last_synced_at.replace(tzinfo=UTC)

    return current_time - last_synced_at >= STEAM_LIBRARY_SYNC_COOLDOWN


async def acquire_steam_library_sync_lock(user_id: int) -> bool:
    redis = cast("Any", await get_redis(RedisPurpose.STEAM))
    return bool(
        await redis.set(
            steam_library_sync_lock_key(user_id),
            "1",
            ex=STEAM_LIBRARY_SYNC_LOCK_TTL_SECONDS,
            nx=True,
        )
    )


async def release_steam_library_sync_lock(user_id: int) -> None:
    redis = cast("Any", await get_redis(RedisPurpose.STEAM))
    await redis.delete(steam_library_sync_lock_key(user_id))


async def _sync_steam_library_async(user_id: int) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await sync_steam_library(db, user_id)
            await db.commit()
    finally:
        await release_steam_library_sync_lock(user_id)


async def sync_steam_library_if_due(
    user_id: int,
    last_synced_at: datetime | None,
) -> None:
    if not is_steam_library_sync_due(last_synced_at):
        return

    if not await acquire_steam_library_sync_lock(user_id):
        return

    await _sync_steam_library_async(user_id)
