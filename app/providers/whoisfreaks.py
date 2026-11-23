"""WhoisFreaks Domain Availability v2 — primary MVP provider."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import httpx

from app.config import get_settings
from app.logging_utils import redact_url
from app.providers.availability_types import AvailabilityBatchResult, AvailabilityItemResult
from app.providers.rate_limit import TokenBucket, backoff_with_jitter, parse_retry_after
from app.services.domains import classify_registrable_domain

log = logging.getLogger(__name__)

WHOISFREAKS_URL = "https://api.whoisfreaks.com/v2.0/domain/availability"
BATCH_MAX = 100

_bucket_lock = threading.Lock()
_bucket: TokenBucket | None = None


def _whoisfreaks_bucket() -> TokenBucket:
    global _bucket
    with _bucket_lock:
        settings = get_settings()
        rpm = float(settings.whoisfreaks_bulk_rpm)
        if _bucket is None:
            _bucket = TokenBucket(rpm)
        return _bucket


def reset_whoisfreaks_bucket_for_tests() -> None:
    global _bucket
    with _bucket_lock:
        _bucket = None


def map_whoisfreaks_status(raw: str | None) -> str:
    """Map provider availability string → TZ §15.6 internal status.

    Never maps unknown/error/unsupported into TAKEN (§15.10.5).
    """
    if not raw:
        return "UNKNOWN"
    v = raw.strip().upper().replace("-", "_").replace(" ", "_")
    if v == "AVAILABLE":
        return "AVAILABLE_PRELIMINARY"
    if v in {"UNAVAILABLE", "TAKEN", "REGISTERED", "NOT_AVAILABLE"}:
        return "TAKEN"
    if "PREMIUM" in v:
        return "PREMIUM"
    if v in {"RESERVED"} or "RESERVED" in v:
        return "RESERVED"
    if v in {"RESTRICTED"} or "RESTRICT" in v:
        return "RESTRICTED"
    if v in {"UNSUPPORTED", "UNSUPPORTED_TLD", "NOT_SUPPORTED", "TLD_NOT_SUPPORTED"}:
        return "UNSUPPORTED_TLD"
    if v in {"INVALID", "MALFORMED", "BAD_DOMAIN"}:
        return "INVALID"
    if v in {"UNKNOWN"}:
        return "UNKNOWN"
    if v in {"ERROR", "FAIL", "FAILED"}:
        return "ERROR"
    return "UNKNOWN"


def refine_availability_status(domain: str, status: str, *, raw: str | None = None) -> str:
    """Upgrade UNKNOWN/ERROR using local PSL classification (§15.5.2)."""
    if status in {"INVALID", "UNSUPPORTED_TLD", "RESTRICTED", "TAKEN", "AVAILABLE_PRELIMINARY", "AVAILABLE_CONFIRMED", "PREMIUM", "RESERVED"}:
        return status
    cls, _code = classify_registrable_domain(domain)
    if cls:
        return cls
    if raw:
        mapped = map_whoisfreaks_status(raw)
        if mapped not in {"UNKNOWN", "ERROR"}:
            return mapped
    return status if status in {"UNKNOWN", "ERROR"} else "UNKNOWN"


class WhoisFreaksProvider:
    name = "whoisfreaks"

    def check_many(self, domains: list[str]) -> AvailabilityBatchResult:
        settings = get_settings()
        if not settings.whoisfreaks_api_key:
            return AvailabilityBatchResult(
                provider=self.name,
                http_status=0,
                items=[],
                credits_actual=0,
                error="WHOISFREAKS_API_KEY not configured",
            )
        if not domains:
            return AvailabilityBatchResult(self.name, 200, [], 0)
        if len(domains) > BATCH_MAX:
            raise ValueError(f"WhoisFreaks batch max {BATCH_MAX}")

        # Local pre-split: do not bill INVALID / UNSUPPORTED_TLD
        api_domains: list[str] = []
        local_items: list[AvailabilityItemResult] = []
        for d in domains:
            key = d.lower()
            cls, code = classify_registrable_domain(key)
            if cls:
                local_items.append(
                    AvailabilityItemResult(
                        domain=key,
                        status=cls,
                        error=code,
                        billed=False,
                        raw={"local_classify": code},
                    )
                )
            else:
                api_domains.append(key)

        if not api_domains:
            return AvailabilityBatchResult(
                provider=self.name,
                http_status=200,
                items=local_items,
                credits_actual=0,
                raw_response={"local_only": True},
            )

        url = f"{WHOISFREAKS_URL}?apiKey={settings.whoisfreaks_api_key}"
        max_retries = max(1, int(settings.whoisfreaks_max_retries))
        base = float(settings.whoisfreaks_retry_base_seconds)
        bucket = _whoisfreaks_bucket()
        last_error: str | None = None
        resp: httpx.Response | None = None
        body: Any = None

        for attempt in range(max_retries):
            bucket.wait(1.0)
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=90.0) as client:
                    resp = client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        content=json.dumps({"domainNames": api_domains}),
                    )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                if attempt + 1 >= max_retries:
                    return AvailabilityBatchResult(
                        provider=self.name,
                        http_status=0,
                        items=local_items,
                        credits_actual=0,
                        error=last_error,
                    )
                time.sleep(backoff_with_jitter(attempt, base=base))
                continue

            if resp.status_code == 429:
                wait = parse_retry_after(resp.headers.get("Retry-After"), default=backoff_with_jitter(attempt, base=base))
                log.warning("WhoisFreaks 429; sleeping %.1fs (attempt %s)", wait, attempt + 1)
                last_error = "rate_limited_429"
                time.sleep(wait)
                if attempt + 1 >= max_retries:
                    return AvailabilityBatchResult(
                        provider=self.name,
                        http_status=429,
                        items=local_items,
                        credits_actual=0,
                        error=last_error,
                    )
                continue

            if resp.status_code >= 500:
                last_error = f"http_{resp.status_code}"
                if attempt + 1 >= max_retries:
                    return AvailabilityBatchResult(
                        provider=self.name,
                        http_status=resp.status_code,
                        items=local_items,
                        credits_actual=0,
                        error=last_error,
                    )
                time.sleep(backoff_with_jitter(attempt, base=base))
                continue

            try:
                body = resp.json()
            except Exception:
                return AvailabilityBatchResult(
                    provider=self.name,
                    http_status=resp.status_code,
                    items=local_items,
                    credits_actual=0,
                    error=f"non-JSON ({redact_url(url)})",
                )
            _ = time.perf_counter() - started
            break
        else:
            return AvailabilityBatchResult(
                provider=self.name,
                http_status=resp.status_code if resp is not None else 0,
                items=local_items,
                credits_actual=0,
                error=last_error or "retries_exhausted",
            )

        assert resp is not None
        items_raw = []
        if isinstance(body, dict):
            items_raw = body.get("bulk_domain_availability_response") or []
        elif isinstance(body, list):
            items_raw = body

        by_domain: dict[str, AvailabilityItemResult] = {}
        for it in items_raw:
            if not isinstance(it, dict):
                continue
            dom = (it.get("domain") or it.get("domainName") or "").lower()
            if not dom:
                continue
            raw_av = it.get("availability") or it.get("domain_availability")
            raw_s = str(raw_av) if raw_av is not None else None
            status = map_whoisfreaks_status(raw_s)
            status = refine_availability_status(dom, status, raw=raw_s)
            err = None
            row_status = it.get("status")
            if row_status and str(row_status).upper() not in {"SUCCESS", "OK", "200"}:
                err = str(row_status)
                # provider row-level unsupported/invalid hints
                mapped_row = map_whoisfreaks_status(str(row_status))
                if mapped_row in {"UNSUPPORTED_TLD", "INVALID", "RESTRICTED", "ERROR"}:
                    status = mapped_row
                    err = mapped_row.lower()
            by_domain[dom] = AvailabilityItemResult(
                domain=dom,
                status=status,
                raw_availability=raw_s,
                error=err,
                is_premium=status == "PREMIUM",
                raw=it,
            )

        items: list[AvailabilityItemResult] = list(local_items)
        for d in api_domains:
            if d in by_domain:
                items.append(by_domain[d])
            else:
                status = refine_availability_status(d, "UNKNOWN")
                items.append(
                    AvailabilityItemResult(
                        domain=d,
                        status=status,
                        error="missing_in_provider_response",
                    )
                )

        # Bill only domains that were sent to the API (1 credit each) on success/partial
        credits = len(api_domains) if resp.status_code in {200, 206} else 0
        return AvailabilityBatchResult(
            provider=self.name,
            http_status=resp.status_code,
            items=items,
            credits_actual=credits,
            raw_response=body if isinstance(body, dict) else {"list": body},
            error=None if resp.status_code in {200, 206} else last_error,
        )


class GoDaddyAvailabilityStub:
    """Deferred until GODADDY_PAT is configured and Spike-confirmed."""

    name = "godaddy_v3"

    def check_many(self, domains: list[str]) -> AvailabilityBatchResult:
        return AvailabilityBatchResult(
            provider=self.name,
            http_status=0,
            items=[],
            credits_actual=0,
            error="GoDaddy confirm deferred (no PAT / not enabled in MVP bootstrap)",
        )
