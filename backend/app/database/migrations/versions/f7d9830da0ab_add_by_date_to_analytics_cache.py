"""add by_date to analytics_cache

Revision ID: f7d9830da0ab
Revises: 965fe85d35fd
Create Date: 2026-06-20 18:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7d9830da0ab"
down_revision: Union[str, None] = "965fe85d35fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analytics_cache",
        sa.Column(
            "by_date",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Pre-aggregated daily violation counts as JSONB",
        ),
    )


def downgrade() -> None:
    op.drop_column("analytics_cache", "by_date")
