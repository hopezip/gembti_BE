from __future__ import annotations

from datetime import date, datetime  # noqa: TC003
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base



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
    trait_vector: Mapped[list[float]] = mapped_column(
        Vector(6), nullable=False, default=[0, 0, 0, 0, 0, 0]
    )
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_korean_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_players_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    steam_detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


