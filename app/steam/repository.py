from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.steam.models import SteamAccount


async def get_steam_account_by_steam_id(
    db: AsyncSession,
    steam_id_64: int,
) -> SteamAccount | None:
    result = await db.execute(
        select(SteamAccount)
        .options(selectinload(SteamAccount.user).selectinload(User.steam_account))
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
