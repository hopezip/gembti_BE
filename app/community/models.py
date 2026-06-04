from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import enum_values

if TYPE_CHECKING:
    from app.auth.models import User
    from app.game.models import Game


class PartyPostCommentStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class PartyPost(Base):
    __tablename__ = "party_posts"

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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    representative_stat_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    comments: Mapped[list[PartyPostComment]] = relationship(
        "PartyPostComment",
        back_populates="post",
        cascade="all, delete-orphan",
    )


class PartyPostComment(Base):
    __tablename__ = "party_post_comment"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("party_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    representative_stat_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[PartyPostCommentStatus] = mapped_column(
        Enum(
            PartyPostCommentStatus,
            name="party_post_comment_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=PartyPostCommentStatus.ACTIVE,
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
    post: Mapped[PartyPost] = relationship(back_populates="comments")
