# games 저장/조회
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Text, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

if TYPE_CHECKING:
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
    "discount_percent",
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


# ── 검색/조회 ─────────────────────────────────────────────────────────────────

_PAGE_SIZE = 12


async def search_games(
    session: AsyncSession,
    q: str,
    page: int,
    sort: str = "relevance",
    filter_genres: list[list[str]] | None = None,
    filter_categories: list[list[str]] | None = None,
) -> tuple[list[Game], int]:
    """제목/장르 ILIKE 검색 + 카테고리(상위)·장르(하위) 서버사이드 필터 + 페이지네이션.

    filter_genres / filter_categories 는 각 원소가 "같은 의미의 DB 값 목록"이다.
    예) filter_genres=[["액션","Action"], ["RPG","롤플레잉 게임","롤플레잉"]]
      → (genres에 액션 OR Action) AND (genres에 RPG OR 롤플레잉 게임 OR 롤플레잉)

    Returns:
        (games, total_count)
    """
    conds: list[Any] = [Game.is_active.is_(True)]
    if q:
        conds.append(
            or_(
                Game.title.ilike(f"%{q}%"),
                cast(Game.genres, Text).ilike(f"%{q}%"),
            )
        )

    # 장르 필터: 선택한 장르 각각을 AND로 적용, 동일 의미 DB 값은 OR
    for db_vals in filter_genres or []:
        conds.append(
            or_(*(cast(Game.genres, Text).ilike(f'%"{v}"%') for v in db_vals))
        )

    # 카테고리(상위) 필터: 선택한 카테고리 각각을 AND로 적용, 동일 의미 DB 값은 OR
    for db_vals in filter_categories or []:
        conds.append(
            or_(*(cast(Game.category, Text).ilike(f'%"{v}"%') for v in db_vals))
        )

    total_result = await session.execute(
        select(func.count()).select_from(Game).where(*conds)
    )
    total = total_result.scalar_one()

    order_by: list = []
    if sort == "rating":
        order_by = [Game.review_score.desc().nulls_last()]
    elif sort == "price_asc":
        order_by = [Game.price_krw.asc().nulls_last()]
    elif sort == "price_desc":
        order_by = [Game.price_krw.desc().nulls_last()]
    elif sort == "release_date":
        order_by = [Game.release_date.desc().nulls_last()]
    else:  # popular
        order_by = [Game.review_count.desc().nulls_last(), Game.review_score.desc().nulls_last()]

    offset = (page - 1) * _PAGE_SIZE
    games_result = await session.execute(
        select(Game).where(*conds).order_by(*order_by).offset(offset).limit(_PAGE_SIZE)
    )
    return list(games_result.scalars().all()), total


async def get_game_by_id(session: AsyncSession, game_id: int) -> Game | None:
    """PK로 활성 게임 1건 조회."""
    result = await session.execute(
        select(Game).where(Game.id == game_id, Game.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def get_developer_games(
    session: AsyncSession,
    developer: str,
    exclude_id: int,
    limit: int = 8,
) -> list[Game]:
    """같은 개발사의 다른 활성 게임 조회."""
    if not developer:
        return []
    result = await session.execute(
        select(Game)
        .where(
            Game.id != exclude_id,
            Game.is_active.is_(True),
            cast(Game.steam_detail_json["developers"], Text).ilike(f"%{developer}%"),
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_trending_games(session: AsyncSession, limit: int = 10) -> list[Game]:
    """동시접속자수 내림차순 (null 제외)."""
    result = await session.execute(
        select(Game)
        .where(Game.is_active.is_(True), Game.current_players.isnot(None))
        .order_by(Game.current_players.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_new_releases(session: AsyncSession, limit: int = 10) -> list[Game]:
    """출시일 최신순 (null 제외)."""
    result = await session.execute(
        select(Game)
        .where(Game.is_active.is_(True), Game.release_date.isnot(None))
        .order_by(Game.release_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_unique_genres(session: AsyncSession) -> list[str]:
    """활성 게임의 고유 장르 목록 (알파벳순)."""
    result = await session.execute(
        text(
            "SELECT DISTINCT json_array_elements_text(genres) AS genre"
            " FROM games WHERE is_active = true ORDER BY genre"
        )
    )
    return [row[0] for row in result.all()]
