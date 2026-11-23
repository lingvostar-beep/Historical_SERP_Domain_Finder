"""Availability jobs / estimate / state — TZ §15 (1d)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AvailabilityJob,
    AvailabilityJobItem,
    AvailabilityProviderUsage,
    DomainAvailabilityState,
    DomainRegistryCheck,
    Run,
    TldRegistrationPolicy,
)
from app.providers.availability_types import AVAILABLE_FILTER
from app.providers.whoisfreaks import BATCH_MAX, WhoisFreaksProvider
from app.services.domains import classify_registrable_domain
from app.services.results import iter_all_domains, _check_age


def _policy_for_domain(db: Session, domain: str) -> TldRegistrationPolicy | None:
    domain = domain.lower()
    policies = db.scalars(select(TldRegistrationPolicy)).all()
    best: TldRegistrationPolicy | None = None
    for p in policies:
        suf = p.suffix.lower()
        if domain == suf or domain.endswith("." + suf):
            if best is None or len(suf) > len(best.suffix):
                best = p
    return best


def _eligibility_for_domain(db: Session, domain: str) -> str:
    best = _policy_for_domain(db, domain)
    if not best:
        return "UNKNOWN"
    return best.eligibility_type


def cctld_warning_for_domain(db: Session, domain: str) -> dict | None:
    """TZ §9.4 — warn about ccTLD / eligibility restrictions separately from availability."""
    best = _policy_for_domain(db, domain)
    if not best:
        return {
            "suffix": None,
            "eligibility_type": "UNKNOWN",
            "restricted": False,
            "policy_url": None,
            "message": (
                "TLD registration policy is unknown for this suffix. "
                "Availability ≠ right to register."
            ),
        }
    if not best.restricted and best.eligibility_type in {"NOT_APPLICABLE", "OPEN"}:
        return None
    return {
        "suffix": best.suffix,
        "eligibility_type": best.eligibility_type,
        "restricted": bool(best.restricted),
        "policy_url": best.policy_url,
        "message": (
            f"ccTLD/zone .{best.suffix}: eligibility={best.eligibility_type}. "
            "A free/available status does not confirm the registrant may register this name; "
            "local eligibility and rights are checked separately."
        ),
    }


def check_history_for_domain(db: Session, domain: str, *, limit: int = 50) -> list[dict]:
    domain = domain.strip().lower()
    rows = db.scalars(
        select(DomainRegistryCheck)
        .where(DomainRegistryCheck.registrable_domain == domain)
        .order_by(DomainRegistryCheck.checked_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return [
        {
            "id": str(c.id),
            "provider": c.provider,
            "status": c.status,
            "raw_availability": c.raw_availability,
            "eligibility_status": c.eligibility_status,
            "checked_at": c.checked_at.isoformat() if c.checked_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "raw_error": c.raw_error,
            "is_premium": bool(c.is_premium),
            "price_amount": float(c.price_amount) if c.price_amount is not None else None,
            "price_currency": c.price_currency,
        }
        for c in rows
    ]


def usd_per_whoisfreaks_credit() -> Decimal:
    return Decimal(str(get_settings().whoisfreaks_reference_usd_per_credit))


def availability_batch_limit(
    *,
    spent_credits: int,
    budget_cap_credits: int,
    spent_usd: Decimal,
    budget_cap_usd: Decimal,
    batch_max: int = BATCH_MAX,
    rate_usd: Decimal | None = None,
) -> int:
    """How many domains may be sent in the next batch under both caps (§15 spend-cap)."""
    rate = rate_usd if rate_usd is not None else usd_per_whoisfreaks_credit()
    credit_room = max(0, int(budget_cap_credits) - int(spent_credits or 0))
    remaining_usd = Decimal(budget_cap_usd) - Decimal(spent_usd or 0)
    if remaining_usd <= 0:
        return 0
    if rate > 0:
        # floor: do not start a domain that would push spent_usd over cap
        usd_room = int(remaining_usd // rate)
    else:
        usd_room = credit_room
    return max(0, min(int(batch_max), credit_room, usd_room))


def estimate_availability(
    db: Session,
    run_id: uuid.UUID,
    *,
    force_refresh: bool = False,
    max_n: int | None = None,
) -> dict:
    if not db.get(Run, run_id):
        raise KeyError("run not found")
    settings = get_settings()
    now = datetime.now(timezone.utc)
    domains = [d["domain"] for d in iter_all_domains(db, run_id) if d.get("domain")]
    if max_n is not None:
        domains = domains[: max(0, max_n)]

    unique = sorted(set(domains))
    invalid: list[str] = []
    cached: list[str] = []
    to_check: list[str] = []

    for dom in unique:
        cls, _code = classify_registrable_domain(dom)
        if cls in {"INVALID", "UNSUPPORTED_TLD"}:
            invalid.append(dom)
            continue
        if not force_refresh:
            st = db.get(DomainAvailabilityState, dom)
            if (
                st
                and st.expires_at
                and st.expires_at > now
                and st.latest_status not in {"UNKNOWN", "ERROR", "NOT_CHECKED", "QUEUED", "CHECKING"}
            ):
                cached.append(dom)
                continue
        to_check.append(dom)

    credits = len(to_check)
    usd = Decimal(str(settings.whoisfreaks_reference_usd_per_credit)) * credits
    batches = (credits + BATCH_MAX - 1) // BATCH_MAX if credits else 0
    return {
        "run_id": str(run_id),
        "total_unique": len(unique),
        "invalid": len(invalid),
        "cached_fresh": len(cached),
        "to_check": credits,
        "projected_credits": credits,
        "projected_usd": str(usd.quantize(Decimal("0.000001"))),
        "batch_count": batches,
        "force_refresh": force_refresh,
        "invalid_samples": invalid[:20],
        "note": "WhoisFreaks: 1 credit per domain, batch ≤100. Separate from DataForSEO budget.",
    }


def maybe_enqueue_auto_after_serp(db: Session, run_id: uuid.UUID) -> uuid.UUID | None:
    """If run.availability_mode=auto_after_serp, create WhoisFreaks job covering all unique domains.

    Returns job id to start asynchronously, or None when skipped.
    """
    run = db.get(Run, run_id)
    if not run or run.availability_mode != "auto_after_serp":
        return None
    if run.status not in {"COMPLETED", "COMPLETED_WITH_GAPS"}:
        return None
    existing = db.scalar(
        select(AvailabilityJob.id).where(AvailabilityJob.run_id == run_id).limit(1)
    )
    if existing:
        return None
    est = estimate_availability(db, run_id, force_refresh=False)
    if est["total_unique"] < 1:
        return None
    # Auto mode: budget = exact projected checks (at least 1 so create_job accepts)
    credits = max(int(est["to_check"]), 1)
    try:
        job = create_availability_job(
            db,
            run_id,
            budget_cap_credits=credits,
            force_refresh=False,
            mode="all_unique",
        )
    except ValueError:
        return None
    db.flush()
    return job.id


def create_availability_job(
    db: Session,
    run_id: uuid.UUID,
    *,
    budget_cap_credits: int,
    budget_cap_usd: Decimal | None = None,
    force_refresh: bool = False,
    mode: str = "all_unique",
    max_n: int | None = None,
    domains_filter: list[str] | None = None,
) -> AvailabilityJob:
    if budget_cap_credits < 1:
        raise ValueError("budget_cap_credits must be >= 1")
    est = estimate_availability(db, run_id, force_refresh=force_refresh, max_n=max_n)
    settings = get_settings()
    rate = usd_per_whoisfreaks_credit()
    if budget_cap_usd is None:
        budget_cap_usd = rate * budget_cap_credits
    budget_cap_usd = Decimal(budget_cap_usd)
    if budget_cap_usd <= 0:
        raise ValueError("budget_cap_usd must be > 0")

    if est["to_check"] > budget_cap_credits:
        raise ValueError(
            f"to_check={est['to_check']} exceeds budget_cap_credits={budget_cap_credits}"
        )
    projected_usd = Decimal(est["projected_usd"])
    if projected_usd > budget_cap_usd:
        raise ValueError(
            f"projected_usd={projected_usd} exceeds budget_cap_usd={budget_cap_usd}"
        )

    domains = [d["domain"] for d in iter_all_domains(db, run_id) if d.get("domain")]
    if domains_filter:
        allow = {x.lower() for x in domains_filter}
        domains = [d for d in domains if d.lower() in allow]
    if max_n is not None:
        domains = domains[:max_n]
    unique = sorted(set(domains))

    now = datetime.now(timezone.utc)
    job = AvailabilityJob(
        run_id=run_id,
        provider="whoisfreaks",
        mode=mode,
        budget_cap_usd=budget_cap_usd,
        budget_cap_credits=budget_cap_credits,
        status="QUEUED",
        force_refresh=force_refresh,
    )
    db.add(job)
    db.flush()

    for dom in unique:
        cls, code = classify_registrable_domain(dom)
        if cls in {"INVALID", "UNSUPPORTED_TLD"}:
            db.add(
                AvailabilityJobItem(
                    job_id=job.id,
                    registrable_domain=dom,
                    status="COMPLETED",
                    last_error=code or cls.lower(),
                    checked_at=now,
                )
            )
            state = db.get(DomainAvailabilityState, dom)
            if not state:
                state = DomainAvailabilityState(registrable_domain=dom)
                db.add(state)
            state.latest_status = cls
            state.last_checked_at = now
            state.expires_at = now + timedelta(hours=settings.whoisfreaks_cache_ttl_hours)
            state.eligibility_status = _eligibility_for_domain(db, dom)
            state.provider = "local_classify"
            continue
        if not force_refresh:
            st = db.get(DomainAvailabilityState, dom)
            if (
                st
                and st.expires_at
                and st.expires_at > now
                and st.latest_status not in {"UNKNOWN", "ERROR", "NOT_CHECKED", "QUEUED", "CHECKING"}
            ):
                db.add(
                    AvailabilityJobItem(
                        job_id=job.id,
                        registrable_domain=dom,
                        status="CACHED",
                        checked_at=st.last_checked_at,
                        check_id=st.last_check_id,
                    )
                )
                continue
        db.add(
            AvailabilityJobItem(
                job_id=job.id,
                registrable_domain=dom,
                status="QUEUED",
            )
        )
    db.flush()
    return job


def job_progress(db: Session, job_id: uuid.UUID) -> dict:
    job = db.get(AvailabilityJob, job_id)
    if not job:
        raise KeyError("job not found")
    by_status = dict(
        db.execute(
            select(AvailabilityJobItem.status, func.count())
            .where(AvailabilityJobItem.job_id == job_id)
            .group_by(AvailabilityJobItem.status)
        ).all()
    )
    return {
        "job_id": str(job.id),
        "run_id": str(job.run_id),
        "status": job.status,
        "provider": job.provider,
        "spent_credits": job.spent_credits,
        "budget_cap_credits": job.budget_cap_credits,
        "spent_usd": str(job.spent_usd),
        "budget_cap_usd": str(job.budget_cap_usd),
        "force_refresh": job.force_refresh,
        "items_by_status": {k: int(v) for k, v in by_status.items()},
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def iter_run_availability(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    available_only: bool = False,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
):
    """Yield availability rows page-by-page (no full materialization)."""
    if not db.get(Run, run_id):
        raise KeyError("run not found")
    for d in iter_all_domains(
        db,
        run_id,
        q=q,
        tld=tld,
        last_seen_before=last_seen_before,
        sort="domain",
        order="asc",
    ):
        dom = d["domain"]
        st = db.get(DomainAvailabilityState, dom)
        latest = st.latest_status if st else "NOT_CHECKED"
        if available_only and latest not in AVAILABLE_FILTER:
            continue
        if status and latest != status:
            continue
        elig = st.eligibility_status if st else _eligibility_for_domain(db, dom)
        check = db.get(DomainRegistryCheck, st.last_check_id) if st and st.last_check_id else None
        error_code = None
        credits_spent = 0
        if check:
            error_code = check.raw_error
            # WhoisFreaks bills 1 credit per domain sent to API; local_classify is free
            if check.provider == "whoisfreaks":
                credits_spent = 1
        elif latest in {"INVALID", "UNSUPPORTED_TLD"}:
            error_code = latest.lower()
            credits_spent = 0
        yield {
            **d,
            "registration_status": latest,
            "eligibility_status": elig,
            "availability_provider": st.provider if st else None,
            "last_checked_at": st.last_checked_at.isoformat() if st and st.last_checked_at else None,
            "expires_at": st.expires_at.isoformat() if st and st.expires_at else None,
            "confirmation_status": st.confirmation_status if st else "NONE",
            "registration_restrictions": elig,
            "freshness": _check_age(st.last_checked_at) if st else None,
            "error_code": error_code,
            "credits_spent": credits_spent,
            "is_premium": bool(check.is_premium) if check else False,
            "price_amount": float(check.price_amount) if check and check.price_amount is not None else None,
            "price_currency": check.price_currency if check else None,
        }


def list_run_availability(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    available_only: bool = False,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    if not db.get(Run, run_id):
        raise KeyError("run not found")
    # UI pagination still needs a total; collect filtered ids lightly then page.
    # Full row dicts for one page only.
    matched: list[dict] = list(
        iter_run_availability(
            db,
            run_id,
            status=status,
            available_only=available_only,
            q=q,
            tld=tld,
            last_seen_before=last_seen_before,
        )
    )
    total = len(matched)
    page = max(1, page)
    page_size = min(max(1, page_size), 500)
    start = (page - 1) * page_size
    slice_items = matched[start : start + page_size]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "available_statuses": sorted(AVAILABLE_FILTER),
        "items": slice_items,
        "warning": "Available statuses are preliminary and may change; TLD eligibility is separate.",
    }


def apply_batch_results(
    db: Session,
    job: AvailabilityJob,
    domains_batch: list[str],
    *,
    http_status: int,
    provider: str,
    items: list,
    credits_actual: int,
    duration_ms: int,
    raw_response: dict,
) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ttl_ok = timedelta(hours=settings.whoisfreaks_cache_ttl_hours)
    ttl_err = timedelta(minutes=15)

    raw_dir = Path(settings.raw_storage_dir) / "availability" / str(job.id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"batch_{now.strftime('%Y%m%dT%H%M%S')}.json"
    # never store apiKey
    raw_path.write_text(json.dumps(raw_response, ensure_ascii=False, indent=2), encoding="utf-8")

    usd = Decimal(str(settings.whoisfreaks_reference_usd_per_credit)) * credits_actual
    db.add(
        AvailabilityProviderUsage(
            job_id=job.id,
            provider=provider,
            batch_id=raw_path.name,
            credits_expected=len(domains_batch),
            credits_actual=credits_actual,
            usd_estimated=usd,
            request_at=now,
            http_status=http_status,
            duration_ms=duration_ms,
        )
    )
    job.spent_credits = (job.spent_credits or 0) + credits_actual
    job.spent_usd = (job.spent_usd or Decimal("0")) + usd

    by_dom = {i.domain.lower(): i for i in items}
    for dom in domains_batch:
        key = dom.lower()
        item_row = db.scalar(
            select(AvailabilityJobItem).where(
                AvailabilityJobItem.job_id == job.id,
                AvailabilityJobItem.registrable_domain == key,
            )
        )
        res = by_dom.get(key)
        if not res:
            status = "ERROR"
            raw_av = None
            err = "missing_result"
        else:
            status = res.status
            raw_av = res.raw_availability
            err = res.error

        expires = now + (ttl_err if status in {"UNKNOWN", "ERROR"} else ttl_ok)
        elig = _eligibility_for_domain(db, key)
        billed = bool(getattr(res, "billed", True)) if res else True
        check_provider = provider if billed else "local_classify"
        check = DomainRegistryCheck(
            registrable_domain=key,
            provider=check_provider,
            status=status,
            raw_availability=raw_av,
            raw_error=err,
            checked_at=now,
            expires_at=expires,
            eligibility_status=elig,
            is_premium=bool(res.is_premium) if res else False,
            raw_response_path=str(raw_path) if billed else None,
        )
        db.add(check)
        db.flush()

        state = db.get(DomainAvailabilityState, key)
        if not state:
            state = DomainAvailabilityState(registrable_domain=key)
            db.add(state)
        # timestamp-aware: only overwrite if this check is newer
        if not state.last_checked_at or state.last_checked_at <= now:
            state.latest_status = status
            state.last_check_id = check.id
            state.last_checked_at = now
            state.expires_at = expires
            state.eligibility_status = elig
            state.provider = check_provider
            if status == "AVAILABLE_CONFIRMED":
                state.confirmation_status = "CONFIRMED"
            elif status == "AVAILABLE_PRELIMINARY":
                state.confirmation_status = "PRELIMINARY"

        if item_row:
            item_row.status = "COMPLETED" if status not in {"ERROR"} else "FAILED"
            item_row.checked_at = now
            item_row.check_id = check.id
            item_row.last_error = err
            item_row.attempt_count = (item_row.attempt_count or 0) + 1

    db.flush()
