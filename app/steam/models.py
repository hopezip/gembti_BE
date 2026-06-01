from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import enum_values
from app.core.database import Base

if TYPE_CHECKING:
    from app.auth.models import User


class SteamSyncStatus(StrEnum):
    SUCCESS = "success"
    PRIVATE = "private"
    FAILED = "failed"
    EMPTY = "empty"


class SteamAccount(Base):
    __tablename__ = "steam_accounts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_steam_accounts_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    steam_id_64: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    steam_sync_status: Mapped[SteamSyncStatus] = mapped_column(
        Enum(SteamSyncStatus, name="steam_sync_status", values_callable=enum_values),
        nullable=False,
        default=SteamSyncStatus.FAILED,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User", back_populates="steam_account")


class UserLibraryGame(Base):
    __tablename__ = "user_library_games"
    __table_args__ = (
        UniqueConstraint("user_id", "steam_app_id", name="uq_user_library_games_user_app"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    steam_app_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    playtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User", back_populates="library_games")
