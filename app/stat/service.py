# 성향 분석 흐름 및 대표 태그 생성
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.stat.repository import get_latest_user_stats
from app.stat.schemas import UserStatsResponse
from app.steam.repository import get_steam_account_by_user_id


async def get_my_latest_stats(db: AsyncSession, user_id: int) -> UserStatsResponse:
    user_stats = await get_latest_user_stats(db, user_id)
    if user_stats is None:
        raise NotFoundException("성향 스탯이 없습니다. 설문을 먼저 완료해 주세요.")

    steam_account = await get_steam_account_by_user_id(db, user_id)

    return UserStatsResponse(
        stats={
            "combat": user_stats.combat,
            "strategy": user_stats.strategy,
            "cooperation": user_stats.cooperation,
            "exploration": user_stats.exploration,
            "growth": user_stats.growth,
            "healing": user_stats.healing,
        },
        source_type=user_stats.source_type.value,
        steam_linked=steam_account is not None,
        last_updated_at=user_stats.created_at,
    )
