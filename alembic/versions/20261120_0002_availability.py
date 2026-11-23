"""availability tables (TZ §15)

Revision ID: 20261120_0002
Revises: 20261119_0001
Create Date: 2026-11-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261120_0002"
down_revision: Union[str, None] = "20261119_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_registry_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("registrable_domain", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("raw_availability", sa.String(128)),
        sa.Column("raw_error", sa.Text()),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("eligibility_status", sa.String(64), nullable=False, server_default="UNKNOWN"),
        sa.Column("price_amount", sa.Numeric(12, 4)),
        sa.Column("price_currency", sa.String(8)),
        sa.Column("is_premium", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("raw_response_path", sa.Text()),
    )
    op.create_index("ix_domain_registry_checks_domain", "domain_registry_checks", ["registrable_domain"])

    op.create_table(
        "domain_availability_state",
        sa.Column("registrable_domain", sa.String(255), primary_key=True),
        sa.Column("latest_status", sa.String(64), nullable=False, server_default="NOT_CHECKED"),
        sa.Column("last_check_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domain_registry_checks.id", ondelete="SET NULL")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("confirmation_status", sa.String(64), nullable=False, server_default="NONE"),
        sa.Column("eligibility_status", sa.String(64), nullable=False, server_default="UNKNOWN"),
        sa.Column("provider", sa.String(64)),
    )
    op.create_index(
        "ix_domain_avail_status_checked",
        "domain_availability_state",
        ["latest_status", "last_checked_at"],
    )

    op.create_table(
        "availability_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="whoisfreaks"),
        sa.Column("mode", sa.String(32), nullable=False, server_default="all_unique"),
        sa.Column("budget_cap_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("budget_cap_credits", sa.Integer(), nullable=False),
        sa.Column("spent_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("spent_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("force_refresh", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_availability_jobs_run_id", "availability_jobs", ["run_id"])

    op.create_table(
        "availability_job_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("availability_jobs.id", ondelete="CASCADE")),
        sa.Column("registrable_domain", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("check_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domain_registry_checks.id", ondelete="SET NULL")),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint("job_id", "registrable_domain"),
    )

    op.create_table(
        "availability_provider_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("availability_jobs.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(128)),
        sa.Column("credits_expected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usd_estimated", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("request_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("http_status", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
    )

    op.create_table(
        "tld_registration_policies",
        sa.Column("suffix", sa.String(64), primary_key=True),
        sa.Column("eligibility_type", sa.String(64), nullable=False, server_default="UNKNOWN"),
        sa.Column("restricted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("policy_url", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )

    # seed priority TLD policies
    op.execute(
        """
        INSERT INTO tld_registration_policies (suffix, eligibility_type, restricted, policy_url)
        VALUES
          ('com.au', 'REQUIRES_EVIDENCE', true, 'https://www.auda.org.au/au-domain-names/the-different-au-domain-names/com-au-domain-names/'),
          ('net.au', 'REQUIRES_EVIDENCE', true, 'https://www.auda.org.au/'),
          ('co.uk', 'REQUIRES_EVIDENCE', true, NULL),
          ('com', 'NOT_APPLICABLE', false, NULL),
          ('net', 'NOT_APPLICABLE', false, NULL),
          ('org', 'NOT_APPLICABLE', false, NULL),
          ('io', 'NOT_APPLICABLE', false, NULL),
          ('de', 'REQUIRES_EVIDENCE', true, NULL)
        ON CONFLICT (suffix) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("tld_registration_policies")
    op.drop_table("availability_provider_usage")
    op.drop_table("availability_job_items")
    op.drop_index("ix_availability_jobs_run_id", table_name="availability_jobs")
    op.drop_table("availability_jobs")
    op.drop_index("ix_domain_avail_status_checked", table_name="domain_availability_state")
    op.drop_table("domain_availability_state")
    op.drop_index("ix_domain_registry_checks_domain", table_name="domain_registry_checks")
    op.drop_table("domain_registry_checks")
