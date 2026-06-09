from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.steam.models import SteamAccount, UserLibraryGame


async def get_steam_account_by_steam_id(
    db: AsyncSession,
    steam_id_64: int,
) -> SteamAccount | None:
    result = await db.execute(
        select(SteamAccount)
        .options(selectinload(SteamAccount.user))
        .where(SteamAccount.steam_id_64 == steam_id_64)
    )
    return result.scalar_one_or_none()


async def get_steam_account_by_user_id(
    db: AsyncSession,
    user_id: int,
) -> SteamAccount | None:
    result = await db.execute(select(SteamAccount).where(SteamAccount.user_id == user_id))
    return result.scalar_one_or_none()


async def save_steam_account(
    db: AsyncSession,
    steam_account: SteamAccount,
) -> SteamAccount:
    db.add(steam_account)
    await db.flush()
    return steam_account


async def get_library_games_by_user_id(
    db: AsyncSession,
    user_id: int,
) -> list[UserLibraryGame]:
    result = await db.execute(
        select(UserLibraryGame)
        .where(UserLibraryGame.user_id == user_id)
        .order_by(UserLibraryGame.playtime_minutes.desc(), UserLibraryGame.steam_app_id.asc())
    )
    return list(result.scalars().all())


async def upsert_library_games(
    db: AsyncSession,
    user_id: int,
    games: list[UserLibraryGame],
) -> int:
    if not games:
        return 0

    steam_app_ids = [game.steam_app_id for game in games]
    result = await db.execute(
        select(UserLibraryGame).where(
            UserLibraryGame.user_id == user_id,
            UserLibraryGame.steam_app_id.in_(steam_app_ids),
        )
    )
    existing_games = {game.steam_app_id: game for game in result.scalars().all()}

    for game in games:
        existing_game = existing_games.get(game.steam_app_id)
        if existing_game is None:
            db.add(game)
            continue

        existing_game.playtime_minutes = game.playtime_minutes
        existing_game.last_played_at = game.last_played_at
        existing_game.synced_at = game.synced_at

    await db.flush()
    return len(games)
