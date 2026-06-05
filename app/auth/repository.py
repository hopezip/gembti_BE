from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User


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


async def save_user(db: AsyncSession, user: User) -> User:
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
