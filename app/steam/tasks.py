import asyncio

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.steam.service import sync_steam_library


async def _sync_steam_library_async(user_id: int) -> dict[str, object]:
    async with AsyncSessionLocal() as db:
        result = await sync_steam_library(db, user_id)
        await db.commit()
        return result.model_dump(mode="json")


@celery_app.task(name="app.steam.tasks.sync_steam_library")
def sync_steam_library_task(user_id: int) -> dict[str, object]:
    return asyncio.run(_sync_steam_library_async(user_id))
