"""add private gender value

Revision ID: c0a6f4d7b8e1
Revises: a57701a8c76e
Create Date: 2026-06-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c0a6f4d7b8e1"
down_revision: Union[str, None] = "a57701a8c76e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE gender ADD VALUE IF NOT EXISTS 'private'")


def downgrade() -> None:
    pass
