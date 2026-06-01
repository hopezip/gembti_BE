from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SupportHelpDocument(Base):
    __tablename__ = "support_help_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)

    doc_category: Mapped[str] = mapped_column(
        Enum(
            "account",
            "steam",
            "survey",
            "result",
            "community",
            "limits",
            "general",
            name="support_help_doc_category",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        server_default="general",
    )

    evidence_status: Mapped[str] = mapped_column(
        Enum(
            "reviewed",
            "generated",
            "deprecated",
            name="support_help_evidence_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        server_default="reviewed",
    )

    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

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

    chunks: Mapped[list["SupportHelpDocChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SupportHelpDocChunk(Base):
    __tablename__ = "support_help_doc_chunks"

    __table_args__ = (
        UniqueConstraint(
            "support_help_document_id",
            "chunk_index",
            name="uq_support_help_doc_chunks_document_chunk_index",
        ),
        Index("ix_support_help_doc_chunks_document_id", "support_help_document_id"),
        Index("ix_support_help_doc_chunks_namespace", "vector_namespace"),
        Index("ix_support_help_doc_chunks_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    support_help_document_id: Mapped[int] = mapped_column(
        ForeignKey("support_help_documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    section_title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)

    keywords: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=text("'[]'::jsonb"),
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default="text-embedding-3-small",
    )

    vector_namespace: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default="support_help",
    )

    embedding_vector: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

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

    document: Mapped["SupportHelpDocument"] = relationship(back_populates="chunks")
