# user_stats 저장/조회
from sqlalchemy.ext.asyncio import AsyncSession

from app.stat.models import StatSourceType, SurveyMode, UserStats


async def create_user_stats(
    db: AsyncSession,
    user_id: int,
    stats: dict[str, int],
    negative_tags: list[str] | None = None,
) -> UserStats:
    user_stats = UserStats(
        user_id=user_id,
        combat=stats["combat"],
        strategy=stats["strategy"],
        cooperation=stats["cooperation"],
        exploration=stats["exploration"],
        growth=stats["growth"],
        healing=stats["healing"],
        source_type=StatSourceType.ONLY_SURVEY,
        survey_mode=SurveyMode.STANDARD,
        negative_tags=negative_tags or [],
    )
    db.add(user_stats)
    await db.flush()
    return user_stats
