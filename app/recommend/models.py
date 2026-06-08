from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import enum_values

if TYPE_CHECKING:
    from app.auth.models import User
    from app.game.models import Game
    from app.stat.models import UserStats


class RecommendationSourceType(StrEnum):
    ONLY_SURVEY = "ONLY_SURVEY"
    HYBRID_STEAM = "HYBRID_STEAM"


class FeedbackType(StrEnum):
    LIKE = "like"
    WISHLIST = "wishlist"
    NOT_INTERESTED = "not_interested"


class RagDocumentType(StrEnum):
    GAME_WIKI = "game_wiki"
    GENRE_GUIDE = "genre_guide"
    TAG_DESC = "tag_desc"
    PERSONA = "persona"
    RECOMMENDATION_RULE = "recommendation_rule"
    GENERAL = "general"


class EvidenceStatus(StrEnum):
    REVIEWED = "reviewed"
    GENERATED = "generated"
    DEPRECATED = "deprecated"


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_stats_id: Mapped[int] = mapped_column(
        ForeignKey("user_stats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[RecommendationSourceType] = mapped_column(
        Enum(
            RecommendationSourceType,
            name="recommendation_source_type",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    similarity_score: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    similarity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")
    user_stats: Mapped[UserStats] = relationship("UserStats")
    game: Mapped[Game] = relationship("Game")


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendation_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, name="recommendation_feedback_type", values_callable=enum_values),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")
    recommendation: Mapped[RecommendationItem] = relationship("RecommendationItem")
    game: Mapped[Game] = relationship("Game")
