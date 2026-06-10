# games, game_tags 저장/조회
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.game.models import Game

_UPDATE_FIELDS = [
    "title",
    "image_url",
    "description",
    "genres",
    "category",
    "trait_vector",
    "release_date",
    "price_krw",
    "is_free",
    "is_korean_supported",
    "is_active",
    "steam_url",
    "review_score",
    "review_count",
    "current_players",
    "current_players_updated_at",
    "steam_detail_json",
]


async def get_all_app_ids(session: AsyncSession) -> list[int]:
    """DB에 저장된 모든 게임의 app_id 반환."""
    result = await session.execute(select(Game.app_id))
    return list(result.scalars().all())


async def upsert_game(session: AsyncSession, game_data: dict) -> None:
    """게임 데이터를 삽입하거나, app_id 충돌 시 업데이트한다."""
    stmt = pg_insert(Game).values(**game_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["app_id"],
        set_={
            **{field: stmt.excluded[field] for field in _UPDATE_FIELDS},
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
