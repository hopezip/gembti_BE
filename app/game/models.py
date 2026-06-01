from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import enum_values
from app.core.database import Base

if TYPE_CHECKING:
    from app.auth.models import User


class SoftDeleteStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    genres: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steam_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
    original_price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_korean_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_players_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    steam_detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GameTag(Base):
    __tablename__ = "game_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    combat_weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    strategy_weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    cooperation_weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    exploration_weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    growth_weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    healing_weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    is_negative_trigger: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    game: Mapped[Game] = relationship("Game")


class GameReview(Base):
    __tablename__ = "game_reviews"
    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_game_reviews_user_game"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_recommended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[SoftDeleteStatus] = mapped_column(
        Enum(SoftDeleteStatus, name="game_review_status", values_callable=enum_values),
        nullable=False,
        default=SoftDeleteStatus.ACTIVE,
    )
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

    user: Mapped[User] = relationship("User")
    game: Mapped[Game] = relationship("Game")
