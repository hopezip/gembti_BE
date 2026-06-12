"""add discount_percent to games

Revision ID: a57701a8c76e
Revises: bfec882c946c
Create Date: 2026-06-09 16:27:20.545368

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a57701a8c76e'
down_revision: Union[str, None] = 'bfec882c946c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('games', sa.Column('discount_percent', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('games', 'discount_percent')
