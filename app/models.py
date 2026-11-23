"""ORM models for TZ §7 (SERP core). Availability tables land in 1d."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    keywords: Mapped[list[ProjectKeyword]] = relationship(back_populates="project")
    targets: Mapped[list[ProjectTarget]] = relationship(back_populates="project")
    runs: Mapped[list[Run]] = relationship(back_populates="project")


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    project_links: Mapped[list[ProjectKeyword]] = relationship(back_populates="keyword")


class ProjectKeyword(Base):
    __tablename__ = "project_keywords"
    __table_args__ = (UniqueConstraint("project_id", "keyword_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id", ondelete="CASCADE"))

    project: Mapped[Project] = relationship(back_populates="keywords")
    keyword: Mapped[Keyword] = relationship(back_populates="project_links")


class ProjectTarget(Base):
    __tablename__ = "project_targets"
    __table_args__ = (UniqueConstraint("project_id", "location_code", "language_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    location_code: Mapped[int] = mapped_column(Integer, nullable=False)
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)

    project: Mapped[Project] = relationship(back_populates="targets")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    budget_cap: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    dedupe_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="registrable_domain")
    availability_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_after_serp")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))

    project: Mapped[Project] = relationship(back_populates="runs")
    queries: Mapped[list[RunQuery]] = relationship(back_populates="run")


class RunQuery(Base):
    __tablename__ = "run_queries"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "keyword_id",
            "location_code",
            "language_code",
            "range_from",
            "range_to",
            name="uq_run_query_matrix",
        ),
        Index(
            "ix_run_queries_queue",
            "run_id",
            "keyword_id",
            "location_code",
            "language_code",
            "range_from",
            "range_to",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id"))
    location_code: Mapped[int] = mapped_column(Integer, nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    range_from: Mapped[date] = mapped_column(Date, nullable=False)
    range_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_task_id: Mapped[Optional[str]] = mapped_column(String(128))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    run: Mapped[Run] = relationship(back_populates="queries")
    snapshots: Mapped[list[SerpSnapshot]] = relationship(back_populates="run_query")


class SerpSnapshot(Base):
    __tablename__ = "serp_snapshots"
    __table_args__ = (
        # Per-run uniqueness: overlapping runs must not steal each other's snapshots
        UniqueConstraint(
            "run_id",
            "provider",
            "keyword_id",
            "location_code",
            "language_code",
            "observed_at",
            name="uq_run_provider_snapshot",
        ),
        Index("ix_serp_snapshots_observed_month", "observed_month"),
        Index("ix_serp_snapshots_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    run_query_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run_queries.id", ondelete="CASCADE"))
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id"))
    location_code: Mapped[int] = mapped_column(Integer, nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    organic_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_json_path: Mapped[Optional[str]] = mapped_column(Text)

    run_query: Mapped[RunQuery] = relationship(back_populates="snapshots")
    results: Mapped[list[SerpResult]] = relationship(back_populates="snapshot")


class SerpResult(Base):
    __tablename__ = "serp_results"
    __table_args__ = (
        Index("ix_serp_results_registrable_domain", "registrable_domain"),
        UniqueConstraint("snapshot_id", "item_order", "result_type", name="uq_snapshot_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("serp_snapshots.id", ondelete="CASCADE"))
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    result_type: Mapped[str] = mapped_column(String(32), nullable=False, default="organic")
    rank_group: Mapped[Optional[int]] = mapped_column(Integer)
    rank_absolute: Mapped[Optional[int]] = mapped_column(Integer)
    url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    hostname: Mapped[Optional[str]] = mapped_column(String(255))
    registrable_domain: Mapped[Optional[str]] = mapped_column(String(255))
    provider_domain: Mapped[Optional[str]] = mapped_column(String(255))
    subdomain: Mapped[Optional[str]] = mapped_column(String(255))

    snapshot: Mapped[SerpSnapshot] = relationship(back_populates="results")


class Coverage(Base):
    __tablename__ = "coverage"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "keyword_id",
            "location_code",
            "language_code",
            "month",
            name="uq_coverage_cell",
        ),
        Index("ix_coverage_run_month_status", "run_id", "month", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id"))
    location_code: Mapped[int] = mapped_column(Integer, nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    organic_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_query_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("run_queries.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    request_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    http_code: Mapped[Optional[int]] = mapped_column(Integer)
    provider_status: Mapped[Optional[int]] = mapped_column(Integer)
    provider_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)


# --- Availability (TZ §15) — Этап 1d ---


class DomainRegistryCheck(Base):
    __tablename__ = "domain_registry_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    registrable_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_availability: Mapped[Optional[str]] = mapped_column(String(128))
    raw_error: Mapped[Optional[str]] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    eligibility_status: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    price_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    price_currency: Mapped[Optional[str]] = mapped_column(String(8))
    is_premium: Mapped[bool] = mapped_column(default=False)
    raw_response_path: Mapped[Optional[str]] = mapped_column(Text)


class DomainAvailabilityState(Base):
    __tablename__ = "domain_availability_state"
    __table_args__ = (Index("ix_domain_avail_status_checked", "latest_status", "last_checked_at"),)

    registrable_domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    latest_status: Mapped[str] = mapped_column(String(64), nullable=False, default="NOT_CHECKED")
    last_check_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("domain_registry_checks.id", ondelete="SET NULL")
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    confirmation_status: Mapped[str] = mapped_column(String(64), nullable=False, default="NONE")
    eligibility_status: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    provider: Mapped[Optional[str]] = mapped_column(String(64))


class AvailabilityJob(Base):
    __tablename__ = "availability_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="whoisfreaks")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="all_unique")
    budget_cap_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    budget_cap_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    spent_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    force_refresh: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[AvailabilityJobItem]] = relationship(back_populates="job")


class AvailabilityJobItem(Base):
    __tablename__ = "availability_job_items"
    __table_args__ = (UniqueConstraint("job_id", "registrable_domain"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("availability_jobs.id", ondelete="CASCADE"))
    registrable_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    check_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("domain_registry_checks.id", ondelete="SET NULL")
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    job: Mapped[AvailabilityJob] = relationship(back_populates="items")


class AvailabilityProviderUsage(Base):
    __tablename__ = "availability_provider_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("availability_jobs.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[Optional[str]] = mapped_column(String(128))
    credits_expected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_actual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usd_estimated: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    request_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class TldRegistrationPolicy(Base):
    __tablename__ = "tld_registration_policies"

    suffix: Mapped[str] = mapped_column(String(64), primary_key=True)
    eligibility_type: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    restricted: Mapped[bool] = mapped_column(default=False)
    policy_url: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
