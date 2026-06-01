from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import enum_values
from app.core.database import Base


class StatAxis(StrEnum):
    COMBAT = "combat"
    STRATEGY = "strategy"
    COOPERATION = "cooperation"
    EXPLORATION = "exploration"
    GROWTH = "growth"
    HEALING = "healing"


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    stat_axis: Mapped[StatAxis] = mapped_column(
        Enum(StatAxis, name="stat_axis", values_callable=enum_values),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
