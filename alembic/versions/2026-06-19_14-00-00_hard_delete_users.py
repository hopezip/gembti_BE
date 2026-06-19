"""replace deferred withdrawal with immediate hard delete

Revision ID: 58e3c9b741ad
Revises: 1f4f7e8c9a2b
Create Date: 2026-06-19 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

revision: str = "58e3c9b741ad"
down_revision: str | None = "1f4f7e8c9a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_user_status_enum(values: tuple[str, ...]) -> None:
    enum_values = ", ".join(f"'{value}'" for value in values)
    op.execute("ALTER TYPE user_status RENAME TO user_status_old")
    op.execute(f"CREATE TYPE user_status AS ENUM ({enum_values})")
    op.execute(
        "ALTER TABLE users ALTER COLUMN status TYPE user_status "
        "USING status::text::user_status"
    )
    op.execute("DROP TYPE user_status_old")


def upgrade() -> None:
    # 유예 중이거나 익명화된 기존 계정은 새 상태 Enum으로 변환하기 전에 완전히 삭제한다.
    op.execute("DELETE FROM users WHERE status::text IN ('withdrawn', 'deleted')")

    op.drop_table("user_withdrawal_requests")
    op.drop_index(op.f("ix_users_hard_delete_after"), table_name="users")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "hard_delete_after")
    op.drop_column("users", "withdrawn_at")

    _replace_user_status_enum(("active", "inactive"))
    op.execute("DROP TYPE IF EXISTS user_withdrawal_status")


def downgrade() -> None:
    _replace_user_status_enum(("active", "inactive", "withdrawn", "deleted"))

    op.add_column("users", sa.Column("withdrawn_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("hard_delete_after", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index(
        op.f("ix_users_hard_delete_after"),
        "users",
        ["hard_delete_after"],
        unique=False,
    )

    op.execute(
        "CREATE TYPE user_withdrawal_status AS ENUM "
        "('REQUESTED', 'CANCELLED', 'HARD_DELETED')"
    )
    withdrawal_status = postgresql.ENUM(
        "REQUESTED",
        "CANCELLED",
        "HARD_DELETED",
        name="user_withdrawal_status",
        create_type=False,
    )
    op.create_table(
        "user_withdrawal_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", withdrawal_status, nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hard_delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hard_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_withdrawal_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_withdrawal_requests")),
    )
    op.create_index(
        op.f("ix_user_withdrawal_requests_hard_delete_after"),
        "user_withdrawal_requests",
        ["hard_delete_after"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_withdrawal_requests_status"),
        "user_withdrawal_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_withdrawal_requests_user_id"),
        "user_withdrawal_requests",
        ["user_id"],
        unique=False,
    )
