"""create support-help RAG tables

Revision ID: 20260530_120616
Revises:
Create Date: 2026-05-30 12:06:16.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = "20260530_120616"
down_revision: Union[str, None] = "f02b0c085ce8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "support_help_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_path", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "doc_category",
            sa.Enum(
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
            ),
            server_default="general",
            nullable=False,
        ),
        sa.Column(
            "evidence_status",
            sa.Enum(
                "reviewed",
                "generated",
                "deprecated",
                name="support_help_evidence_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="reviewed",
            nullable=False,
        ),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_path", name="uq_support_help_documents_source_path"),
    )

    op.create_table(
        "support_help_doc_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("support_help_document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("section_title", sa.String(length=300), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            server_default="text-embedding-3-small",
            nullable=False,
        ),
        sa.Column(
            "vector_namespace", sa.String(length=100), server_default="support_help", nullable=False
        ),
        sa.Column("embedding_vector", Vector(1536), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["support_help_document_id"],
            ["support_help_documents.id"],
            name="fk_support_help_doc_chunks_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "support_help_document_id",
            "chunk_index",
            name="uq_support_help_doc_chunks_document_chunk_index",
        ),
    )

    op.create_index(
        "ix_support_help_doc_chunks_document_id",
        "support_help_doc_chunks",
        ["support_help_document_id"],
    )
    op.create_index(
        "ix_support_help_doc_chunks_namespace",
        "support_help_doc_chunks",
        ["vector_namespace"],
    )
    op.create_index(
        "ix_support_help_doc_chunks_content_hash",
        "support_help_doc_chunks",
        ["content_hash"],
    )
    op.create_index(
        "ix_support_help_doc_chunks_embedding_vector_hnsw",
        "support_help_doc_chunks",
        ["embedding_vector"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_help_doc_chunks_embedding_vector_hnsw",
        table_name="support_help_doc_chunks",
        postgresql_using="hnsw",
    )
    op.drop_index("ix_support_help_doc_chunks_content_hash", table_name="support_help_doc_chunks")
    op.drop_index("ix_support_help_doc_chunks_namespace", table_name="support_help_doc_chunks")
    op.drop_index("ix_support_help_doc_chunks_document_id", table_name="support_help_doc_chunks")
    op.drop_table("support_help_doc_chunks")
    op.drop_table("support_help_documents")
