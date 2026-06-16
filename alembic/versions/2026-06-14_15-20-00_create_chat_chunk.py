"""create chat_chunk table

Revision ID: 1f4f7e8c9a2b
Revises: ab6bf4578a8f
Create Date: 2026-06-14 15:20:00.000000

"""

from collections.abc import Sequence
from typing import Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

revision: str = "1f4f7e8c9a2b"
down_revision: str | None = "ab6bf4578a8f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chat_chunk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_vector", Vector(1536), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_chunk")),
    )


def downgrade() -> None:
    op.drop_table("chat_chunk")
