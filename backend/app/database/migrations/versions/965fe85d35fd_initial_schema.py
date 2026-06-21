"""Initial schema: violations, vehicles, analytics_cache tables with indexes.

Revision ID: 965fe85d35fd
Revises: 
Create Date: 2025-01-01 00:00:00.000000

This migration creates all three tables and their associated indexes as
defined in the ORM models (backend/app/database/models.py) and the design
document.

Requirements: 3.5
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "965fe85d35fd"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # vehicles
    # ------------------------------------------------------------------
    op.create_table(
        "vehicles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            comment="UUID primary key",
        ),
        sa.Column(
            "image_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
            comment="UUID of the source image (no DB-level FK constraint)",
        ),
        sa.Column(
            "vehicle_class",
            sa.String(32),
            nullable=False,
            comment="Detected vehicle class label",
        ),
        sa.Column(
            "bounding_box",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Bounding box coordinates as JSONB",
        ),
        sa.Column(
            "plate_number",
            sa.String(20),
            nullable=True,
            comment="OCR-extracted plate number, nullable",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Row creation timestamp (UTC)",
        ),
    )
    op.create_index(
        "idx_vehicles_image_id",
        "vehicles",
        ["image_id"],
    )

    # ------------------------------------------------------------------
    # violations
    # ------------------------------------------------------------------
    op.create_table(
        "violations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            comment="UUID primary key",
        ),
        sa.Column(
            "image_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
            comment="UUID of the source image",
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
            comment="FK to vehicles.id; SET NULL when the vehicle row is deleted",
        ),
        sa.Column(
            "violation_type",
            sa.String(64),
            nullable=False,
            comment="Violation type label, e.g. HELMET_NON_COMPLIANCE",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            comment="ML model confidence in [0.0, 1.0]",
        ),
        sa.Column(
            "bounding_box",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Bounding box coordinates as JSONB",
        ),
        sa.Column(
            "plate_number",
            sa.String(20),
            nullable=True,
            comment="Associated plate number, nullable",
        ),
        sa.Column(
            "annotated_image_path",
            sa.Text(),
            nullable=True,
            comment="MinIO object path for the annotated image; null if generation failed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Row creation timestamp (UTC)",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name="chk_violations_confidence_range",
        ),
    )
    op.create_index(
        "idx_violations_image_id",
        "violations",
        ["image_id"],
    )
    op.create_index(
        "idx_violations_type",
        "violations",
        ["violation_type"],
    )
    op.create_index(
        "idx_violations_created_at",
        "violations",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "idx_violations_plate",
        "violations",
        ["plate_number"],
    )

    # ------------------------------------------------------------------
    # analytics_cache
    # ------------------------------------------------------------------
    op.create_table(
        "analytics_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            comment="UUID primary key",
        ),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Start of the aggregation window (UTC, inclusive)",
        ),
        sa.Column(
            "window_end",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="End of the aggregation window (UTC, inclusive)",
        ),
        sa.Column(
            "violation_type",
            sa.String(64),
            nullable=False,
            comment="Violation type label this count row applies to",
        ),
        sa.Column(
            "count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Pre-aggregated violation count",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Timestamp of last cache write (used for 5-minute TTL check)",
        ),
        sa.UniqueConstraint(
            "window_start",
            "window_end",
            "violation_type",
            name="idx_analytics_window_type",
        ),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order (violations references vehicles).
    op.drop_table("analytics_cache")

    op.drop_index("idx_violations_plate", table_name="violations")
    op.drop_index("idx_violations_created_at", table_name="violations")
    op.drop_index("idx_violations_type", table_name="violations")
    op.drop_index("idx_violations_image_id", table_name="violations")
    op.drop_table("violations")

    op.drop_index("idx_vehicles_image_id", table_name="vehicles")
    op.drop_table("vehicles")
