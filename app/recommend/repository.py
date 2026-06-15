# recommendations, audits, feedbacks 저장/조회
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.game.models import Game
from app.recommend.models import RecommendationItem, RecommendationSourceType
from app.stat.models import UserStats
from app.steam.models import UserLibraryGame

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_latest_user_stats(db: AsyncSession, user_id: int) -> UserStats | None:
    result = await db.execute(
        select(UserStats)
        .where(UserStats.user_id == user_id)
        .order_by(UserStats.created_at.desc(), UserStats.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_recommendable_games(
    db: AsyncSession,
    candidate_limit: int = 500,
    excluded_app_ids: Sequence[int] | None = None,
) -> list[Game]:
    query = select(Game).where(Game.is_active.is_(True))
    if excluded_app_ids:
        query = query.where(Game.app_id.not_in(excluded_app_ids))

    result = await db.execute(query.order_by(Game.id).limit(candidate_limit))
    return list(result.scalars().all())


async def get_user_library_steam_app_ids(db: AsyncSession, user_id: int) -> list[int]:
    result = await db.execute(
        select(UserLibraryGame.steam_app_id).where(UserLibraryGame.user_id == user_id)
    )
    return list(result.scalars().all())


async def save_recommendation_items(
    db: AsyncSession,
    user_id: int,
    user_stats: UserStats,
    ranked_games: list[tuple[Game, float]],
) -> list[RecommendationItem]:
    items: list[RecommendationItem] = []

    for rank, (game, similarity_score) in enumerate(ranked_games, start=1):
        item = RecommendationItem(
            user_id=user_id,
            user_stats_id=user_stats.id,
            source_type=RecommendationSourceType(user_stats.source_type.value),
            game_id=game.id,
            similarity_score=Decimal(str(round(similarity_score, 6))),
            # db 저장은 numeric이라 decimal 표기. api 응답에서 float으로 출력됩니다.
            similarity_rank=rank,
        )
        db.add(item)
        items.append(item)

    await db.flush()
    return items


async def get_latest_recommendation_items(
    db: AsyncSession,
    user_id: int,
) -> list[RecommendationItem]:
    latest_created_at_subquery = (
        select(RecommendationItem.created_at)
        .where(RecommendationItem.user_id == user_id)
        .order_by(RecommendationItem.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )

    result = await db.execute(
        select(RecommendationItem)
        .where(
            RecommendationItem.user_id == user_id,
            RecommendationItem.created_at == latest_created_at_subquery,
        )
        .options(selectinload(RecommendationItem.game))
        .order_by(RecommendationItem.similarity_rank.asc())
    )
    return list(result.scalars().all())
