from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.game.models import Game
from app.stat.models import UserStats
from app.steam.models import UserLibraryGame


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.steam_account)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.steam_account))
        .where(User.email == email.strip().lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_nickname(db: AsyncSession, nickname: str) -> User | None:
    result = await db.execute(select(User).where(User.nickname == nickname))
    return result.scalar_one_or_none()


async def has_user_stats(db: AsyncSession, user_id: int) -> bool:
    result = await db.execute(select(UserStats.id).where(UserStats.user_id == user_id).limit(1))
    return result.scalar_one_or_none() is not None


async def get_user_steam_library_rows(
    db: AsyncSession,
    user_id: int,
) -> list[tuple[UserLibraryGame, Game | None]]:
    result = await db.execute(
        select(UserLibraryGame, Game)
        .outerjoin(Game, Game.app_id == UserLibraryGame.steam_app_id)
        .where(UserLibraryGame.user_id == user_id)
        .order_by(
            UserLibraryGame.playtime_minutes.desc(),
            UserLibraryGame.last_played_at.desc().nullslast(),
            UserLibraryGame.steam_app_id.asc(),
        )
    )
    return [(library_game, game) for library_game, game in result.all()]


async def save_user(db: AsyncSession, user: User) -> User:
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user_by_id(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()
