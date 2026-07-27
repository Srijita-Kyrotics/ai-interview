"""Add rate_limits and response_cache tables.

Revision ID: 002
Revises: 001
Create Date: 2026-07-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("timestamps", JSONB, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.Float, nullable=False),
    )

    op.create_table(
        "response_cache",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
    )
    op.create_index("idx_response_cache_expires", "response_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_response_cache_expires", "response_cache")
    op.drop_table("response_cache")
    op.drop_table("rate_limits")
