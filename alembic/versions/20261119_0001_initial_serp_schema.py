"""initial SERP schema (TZ §7)

Revision ID: 20261119_0001
Revises:
Create Date: 2026-11-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261119_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "project_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("keywords.id", ondelete="CASCADE")),
        sa.UniqueConstraint("project_id", "keyword_id"),
    )
    op.create_table(
        "project_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("location_name", sa.String(255), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.UniqueConstraint("project_id", "location_code", "language_code"),
    )
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("budget_cap", sa.Numeric(12, 6), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("dedupe_mode", sa.String(32), nullable=False, server_default="registrable_domain"),
        sa.Column("availability_mode", sa.String(32), nullable=False, server_default="manual_after_serp"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("spent_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
    )
    op.create_table(
        "run_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE")),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("keywords.id")),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("range_from", sa.Date(), nullable=False),
        sa.Column("range_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_task_id", sa.String(128)),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint(
            "run_id",
            "keyword_id",
            "location_code",
            "language_code",
            "range_from",
            "range_to",
            name="uq_run_query_matrix",
        ),
    )
    op.create_index(
        "ix_run_queries_queue",
        "run_queries",
        ["run_id", "keyword_id", "location_code", "language_code", "range_from", "range_to"],
    )
    op.create_table(
        "serp_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_query_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("run_queries.id", ondelete="CASCADE")),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("keywords.id")),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_month", sa.String(7), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("organic_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_json_path", sa.Text()),
        sa.UniqueConstraint(
            "provider",
            "keyword_id",
            "location_code",
            "language_code",
            "observed_at",
            name="uq_provider_snapshot",
        ),
    )
    op.create_index("ix_serp_snapshots_observed_month", "serp_snapshots", ["observed_month"])
    op.create_table(
        "serp_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("serp_snapshots.id", ondelete="CASCADE")),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.Column("result_type", sa.String(32), nullable=False, server_default="organic"),
        sa.Column("rank_group", sa.Integer()),
        sa.Column("rank_absolute", sa.Integer()),
        sa.Column("url", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("hostname", sa.String(255)),
        sa.Column("registrable_domain", sa.String(255)),
        sa.Column("provider_domain", sa.String(255)),
        sa.Column("subdomain", sa.String(255)),
        sa.UniqueConstraint("snapshot_id", "item_order", "result_type", name="uq_snapshot_item"),
    )
    op.create_index("ix_serp_results_registrable_domain", "serp_results", ["registrable_domain"])
    op.create_table(
        "coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE")),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("keywords.id")),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organic_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "run_id",
            "keyword_id",
            "location_code",
            "language_code",
            "month",
            name="uq_coverage_cell",
        ),
    )
    op.create_index("ix_coverage_run_month_status", "coverage", ["run_id", "month", "status"])
    op.create_table(
        "api_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_query_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("run_queries.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("request_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("http_code", sa.Integer()),
        sa.Column("provider_status", sa.Integer()),
        sa.Column("provider_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("meta", postgresql.JSONB()),
    )


def downgrade() -> None:
    op.drop_table("api_usage")
    op.drop_index("ix_coverage_run_month_status", table_name="coverage")
    op.drop_table("coverage")
    op.drop_index("ix_serp_results_registrable_domain", table_name="serp_results")
    op.drop_table("serp_results")
    op.drop_index("ix_serp_snapshots_observed_month", table_name="serp_snapshots")
    op.drop_table("serp_snapshots")
    op.drop_index("ix_run_queries_queue", table_name="run_queries")
    op.drop_table("run_queries")
    op.drop_table("runs")
    op.drop_table("project_targets")
    op.drop_table("project_keywords")
    op.drop_table("keywords")
    op.drop_table("projects")
