from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import enum_values
from app.core.database import Base

if TYPE_CHECKING:
    from app.steam.models import SteamAccount, UserLibraryGame


class LoginProvider(StrEnum):
    EMAIL = "email"
    STEAM = "steam"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    WITHDRAWN = "withdrawn"
    DELETED = "deleted"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class EmailVerificationPurpose(StrEnum):
    SIGNUP = "SIGNUP"
    PASSWORD_RESET = "PASSWORD_RESET"


class EmailVerificationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"


class UserWithdrawalStatus(StrEnum):
    REQUESTED = "REQUESTED"
    CANCELLED = "CANCELLED"
    HARD_DELETED = "HARD_DELETED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(160), nullable=True)
    login_provider: Mapped[LoginProvider] = mapped_column(
        Enum(LoginProvider, name="login_provider", values_callable=enum_values),
        nullable=False,
        default=LoginProvider.EMAIL,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", values_callable=enum_values),
        nullable=False,
        default=UserStatus.ACTIVE,
        index=True,
    )
    gender: Mapped[Gender | None] = mapped_column(
        Enum(Gender, name="gender", values_callable=enum_values),
        nullable=True,
    )
    birth_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hard_delete_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    steam_account: Mapped[SteamAccount | None] = relationship(
        "SteamAccount",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    library_games: Mapped[list[UserLibraryGame]] = relationship(
        "UserLibraryGame",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    email_verifications: Mapped[list[EmailVerification]] = relationship(
        "EmailVerification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    withdrawal_requests: Mapped[list[UserWithdrawalRequest]] = relationship(
        "UserWithdrawalRequest",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    purpose: Mapped[EmailVerificationPurpose] = mapped_column(
        Enum(
            EmailVerificationPurpose,
            name="email_verification_purpose",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    status: Mapped[EmailVerificationStatus] = mapped_column(
        Enum(
            EmailVerificationStatus,
            name="email_verification_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=EmailVerificationStatus.PENDING,
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User | None] = relationship(back_populates="email_verifications")


class UserWithdrawalRequest(Base):
    __tablename__ = "user_withdrawal_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[UserWithdrawalStatus] = mapped_column(
        Enum(
            UserWithdrawalStatus,
            name="user_withdrawal_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=UserWithdrawalStatus.REQUESTED,
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    hard_delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    hard_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="withdrawal_requests")
