from redis.asyncio import Redis, from_url

from app.core.config import settings
from app.core.enums import RedisPurpose

_redis_clients: dict[RedisPurpose, Redis] = {}


def get_redis_url(purpose: RedisPurpose) -> str:
    purpose_urls = {
        RedisPurpose.AUTH: settings.REDIS_AUTH_URL,
        RedisPurpose.EMAIL: settings.REDIS_EMAIL_URL,
        RedisPurpose.STEAM: settings.REDIS_STEAM_URL,
    }
    return purpose_urls[purpose] or settings.REDIS_URL


async def get_redis(purpose: RedisPurpose) -> Redis:
    if purpose not in _redis_clients:
        _redis_clients[purpose] = from_url(
            get_redis_url(purpose),
            decode_responses=True,
        )
    return _redis_clients[purpose]


async def close_redis() -> None:
    for redis_client in _redis_clients.values():
        await redis_client.aclose()
    _redis_clients.clear()
