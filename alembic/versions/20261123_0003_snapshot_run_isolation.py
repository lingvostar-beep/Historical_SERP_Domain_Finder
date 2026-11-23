"""Run-scoped SERP snapshot uniqueness — stop cross-run snapshot theft.

Revision ID: 20261123_0003
Revises: 20261120_0002
Create Date: 2026-11-23

Global uq_provider_snapshot (provider, keyword, loc, lang, observed_at) caused
a later overlapping run to re-link SerpSnapshot.run_query_id and silently empty
earlier runs' Domains/Positions. Scope uniqueness per run_id instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261123_0003"
down_revision = "20261120_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "serp_snapshots",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Backfill from owning run_query
    op.execute(
        """
        UPDATE serp_snapshots AS s
        SET run_id = q.run_id
        FROM run_queries AS q
        WHERE s.run_query_id = q.id
        """
    )
    # Orphans (should not exist) — drop rather than leave NULL
    op.execute("DELETE FROM serp_snapshots WHERE run_id IS NULL")
    op.alter_column(
        "serp_snapshots",
        "run_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_serp_snapshots_run_id",
        "serp_snapshots",
        "runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_serp_snapshots_run_id", "serp_snapshots", ["run_id"])

    op.drop_constraint("uq_provider_snapshot", "serp_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_run_provider_snapshot",
        "serp_snapshots",
        [
            "run_id",
            "provider",
            "keyword_id",
            "location_code",
            "language_code",
            "observed_at",
        ],
    )


def downgrade() -> None:
    op.drop_constraint("uq_run_provider_snapshot", "serp_snapshots", type_="unique")
    # Downgrade may fail if two runs share the same provider snapshot key
    op.create_unique_constraint(
        "uq_provider_snapshot",
        "serp_snapshots",
        [
            "provider",
            "keyword_id",
            "location_code",
            "language_code",
            "observed_at",
        ],
    )
    op.drop_index("ix_serp_snapshots_run_id", table_name="serp_snapshots")
    op.drop_constraint("fk_serp_snapshots_run_id", "serp_snapshots", type_="foreignkey")
    op.drop_column("serp_snapshots", "run_id")
