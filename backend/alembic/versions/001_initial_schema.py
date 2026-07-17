"""Initial schema — users, sessions, otp_state, captcha_state, proctoring_logs.

Revision ID: 001
Revises:
Create Date: 2026-07-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("salt", sa.Text, nullable=False),
        sa.Column("hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.Float, nullable=False),
    )

    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, nullable=False, server_default=""),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_updated_at", "sessions", ["updated_at"])

    op.create_table(
        "otp_state",
        sa.Column("email", sa.Text, primary_key=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )

    op.create_table(
        "captcha_state",
        sa.Column("token", sa.Text, primary_key=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )

    op.create_table(
        "proctoring_logs",
        sa.Column("session_id", sa.Text, primary_key=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("proctoring_logs")
    op.drop_table("captcha_state")
    op.drop_table("otp_state")
    op.drop_table("sessions")
    op.drop_table("users")
