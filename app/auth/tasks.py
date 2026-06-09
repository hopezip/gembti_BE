import asyncio

from app.auth.service import cleanup_expired_withdrawn_users
from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal


async def _cleanup_withdrawn_users_async() -> int:
    async with AsyncSessionLocal() as db:
        return await cleanup_expired_withdrawn_users(db)


@celery_app.task(name="app.auth.tasks.cleanup_withdrawn_users")
def cleanup_withdrawn_users() -> int:
    return asyncio.run(_cleanup_withdrawn_users_async())
