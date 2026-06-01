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

from app.common.enums import enum_values
from app.core.database import Base

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


class Recommendation(Base):
    __tablename__ = "recommendations"

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
    match_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warning_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflicting_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")
    user_stats: Mapped[UserStats] = relationship("UserStats")
    game: Mapped[Game] = relationship("Game")


class RecommendationAudit(Base):
    __tablename__ = "recommendation_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[RecommendationSourceType] = mapped_column(
        Enum(
            RecommendationSourceType,
            name="recommendation_audit_source_type",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    snapshot_combat: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_strategy: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_cooperation: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_exploration: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_growth: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_healing: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    excluded_game_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    override_filters: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User")
    recommendation: Mapped[Recommendation | None] = relationship("Recommendation")


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"),
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
    recommendation: Mapped[Recommendation] = relationship("Recommendation")
    game: Mapped[Game] = relationship("Game")


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int | None] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    doc_type: Mapped[RagDocumentType] = mapped_column(
        Enum(RagDocumentType, name="rag_document_type", values_callable=enum_values),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_status: Mapped[EvidenceStatus] = mapped_column(
        Enum(EvidenceStatus, name="rag_evidence_status", values_callable=enum_values),
        nullable=False,
        default=EvidenceStatus.REVIEWED,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vector_namespace: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="recommendation_evidence",
    )
    vector_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
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

    game: Mapped[Game | None] = relationship("Game")
