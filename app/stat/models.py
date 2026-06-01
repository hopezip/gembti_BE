from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import enum_values
from app.core.database import Base

if TYPE_CHECKING:
    from app.auth.models import User


class StatSourceType(StrEnum):
    ONLY_SURVEY = "ONLY_SURVEY"
    HYBRID_STEAM = "HYBRID_STEAM"


class SurveyMode(StrEnum):
    STANDARD = "standard"
    CHATBOT = "chatbot"


class UserStats(Base):
    __tablename__ = "user_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    combat: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[int] = mapped_column(Integer, nullable=False)
    cooperation: Mapped[int] = mapped_column(Integer, nullable=False)
    exploration: Mapped[int] = mapped_column(Integer, nullable=False)
    growth: Mapped[int] = mapped_column(Integer, nullable=False)
    healing: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[StatSourceType] = mapped_column(
        Enum(StatSourceType, name="stat_source_type", values_callable=enum_values),
        nullable=False,
    )
    survey_mode: Mapped[SurveyMode | None] = mapped_column(
        Enum(SurveyMode, name="survey_mode", values_callable=enum_values),
        nullable=True,
    )
    negative_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    primary_tag_1: Mapped[str | None] = mapped_column(String(50), nullable=True)
    primary_tag_2: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")
