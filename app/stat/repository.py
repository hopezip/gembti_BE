# user_stats 저장/조회
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.game.models import Game
from app.stat.models import StatSourceType, SurveyMode, UserStats
from app.steam.models import UserLibraryGame


async def create_user_stats(
    db: AsyncSession,
    user_id: int,
    stats: dict[str, int],
    source_type: StatSourceType = StatSourceType.ONLY_SURVEY,
    survey_mode: SurveyMode | None = SurveyMode.STANDARD,
    negative_tags: list[str] | None = None,
) -> UserStats:
    user_stats = await get_latest_user_stats(db, user_id)

    if user_stats is None:
        user_stats = UserStats(
            user_id=user_id,
            combat=stats["combat"],
            strategy=stats["strategy"],
            cooperation=stats["cooperation"],
            exploration=stats["exploration"],
            growth=stats["growth"],
            healing=stats["healing"],
            source_type=source_type,
            survey_mode=survey_mode,
            negative_tags=negative_tags or [],
        )
        db.add(user_stats)
    else:
        user_stats.combat = stats["combat"]
        user_stats.strategy = stats["strategy"]
        user_stats.cooperation = stats["cooperation"]
        user_stats.exploration = stats["exploration"]
        user_stats.growth = stats["growth"]
        user_stats.healing = stats["healing"]
        user_stats.source_type = source_type
        user_stats.survey_mode = survey_mode
        if negative_tags is not None:
            user_stats.negative_tags = negative_tags

    await db.flush()
    return user_stats


async def get_latest_user_stats(
    db: AsyncSession,
    user_id: int,
) -> UserStats | None:
    result = await db.execute(
        select(UserStats)
        .where(UserStats.user_id == user_id)
        .order_by(UserStats.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_user_steam_game_trait_vectors(
    db: AsyncSession,
    user_id: int,
) -> list[list[float]]:
    result = await db.execute(
        select(Game.trait_vector)
        .join(UserLibraryGame, UserLibraryGame.steam_app_id == Game.app_id)
        .where(
            UserLibraryGame.user_id == user_id,
            Game.is_active.is_(True),
        )
    )
    return [
        [float(value) for value in vector]
        for vector in result.scalars().all()
        if vector is not None
    ]
