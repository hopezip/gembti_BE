from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User, UserWithdrawalRequest, UserWithdrawalStatus
from app.core.enums import UserStatus
from app.stat.models import UserStats


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


async def save_user(db: AsyncSession, user: User) -> User:
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_requested_withdrawal_by_user_id(
    db: AsyncSession,
    user_id: int,
) -> UserWithdrawalRequest | None:
    result = await db.execute(
        select(UserWithdrawalRequest).where(
            UserWithdrawalRequest.user_id == user_id,
            UserWithdrawalRequest.status == UserWithdrawalStatus.REQUESTED,
        )
    )
    return result.scalar_one_or_none()


async def get_expired_withdrawal_requests(
    db: AsyncSession,
    now: datetime,
) -> list[UserWithdrawalRequest]:
    result = await db.execute(
        select(UserWithdrawalRequest)
        .options(selectinload(UserWithdrawalRequest.user))
        .join(User)
        .where(
            UserWithdrawalRequest.status == UserWithdrawalStatus.REQUESTED,
            UserWithdrawalRequest.hard_delete_after <= now,
            User.status == UserStatus.WITHDRAWN,
            User.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())
