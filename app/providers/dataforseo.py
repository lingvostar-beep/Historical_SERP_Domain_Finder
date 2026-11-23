from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.providers.dates import validate_history_window
from app.providers.types import (
    HistoricalSnapshot,
    OrganicItem,
    SerpFetchRequest,
    SerpFetchResult,
)

LEGACY_URL = "https://api.dataforseo.com/v3/dataforseo_labs/historical_serps/live"
CURRENT_URL = "https://api.dataforseo.com/v3/dataforseo_labs/google/historical_serps/live"


def _auth_header(login: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _parse_observed_at(value: str) -> datetime:
    # DataForSEO: "2026-01-10 01:48:32 +00:00"
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _organic_items(snapshot: dict[str, Any]) -> list[OrganicItem]:
    out: list[OrganicItem] = []
    order = 0
    for it in snapshot.get("items") or []:
        if not isinstance(it, dict):
            continue
        if it.get("type") != "organic":
            continue
        out.append(
            OrganicItem(
                rank_group=it.get("rank_group"),
                rank_absolute=it.get("rank_absolute"),
                url=it.get("url"),
                title=it.get("title"),
                domain=it.get("domain"),
                item_order=order,
                raw=it,
            )
        )
        order += 1
    return out


def parse_historical_response(body: dict[str, Any], provider: str) -> SerpFetchResult:
    tasks = body.get("tasks") or []
    task = tasks[0] if tasks else {}
    snapshots: list[HistoricalSnapshot] = []

    for res in task.get("result") or []:
        if not isinstance(res, dict):
            continue
        for snap in res.get("items") or []:
            if not isinstance(snap, dict):
                continue
            dt_raw = snap.get("datetime")
            if not dt_raw:
                continue
            observed_at = _parse_observed_at(str(dt_raw))
            organics = _organic_items(snap)
            snapshots.append(
                HistoricalSnapshot(
                    observed_at=observed_at,
                    observed_month=observed_at.strftime("%Y-%m"),
                    provider=provider,
                    organic_items=organics,
                    organic_count=len(organics),
                    raw_snapshot=snap,
                )
            )

    cost = body.get("cost")
    if cost is None and tasks:
        cost = sum((t.get("cost") or 0) for t in tasks if isinstance(t, dict))

    return SerpFetchResult(
        provider=provider,
        http_status=200,
        top_status_code=body.get("status_code"),
        task_status_code=task.get("status_code"),
        task_status_message=task.get("status_message"),
        cost_usd=Decimal(str(cost or 0)),
        snapshots=snapshots,
        raw_response=body,
    )


class _DataForSeoBase:
    name: str
    endpoint: str

    def fetch(self, request: SerpFetchRequest) -> SerpFetchResult:
        settings = get_settings()
        if not settings.dataforseo_login or not settings.dataforseo_password:
            return SerpFetchResult(
                provider=self.name,
                http_status=0,
                top_status_code=None,
                task_status_code=None,
                task_status_message=None,
                cost_usd=Decimal("0"),
                snapshots=[],
                error="DATAFORSEO_LOGIN/PASSWORD not configured",
            )

        try:
            date_from, date_to = validate_history_window(request.date_from, request.date_to)
        except ValueError as exc:
            return SerpFetchResult(
                provider=self.name,
                http_status=0,
                top_status_code=None,
                task_status_code=40501,
                task_status_message=str(exc),
                cost_usd=Decimal("0"),
                snapshots=[],
                error=str(exc),
            )

        if not request.location_code and not request.location_name:
            return SerpFetchResult(
                provider=self.name,
                http_status=0,
                top_status_code=None,
                task_status_code=None,
                task_status_message=None,
                cost_usd=Decimal("0"),
                snapshots=[],
                error="location_code or location_name is required",
            )

        payload_item: dict[str, Any] = {
            "keyword": request.keyword,
            "language_code": request.language_code,
        }
        if request.location_code is not None:
            payload_item["location_code"] = request.location_code
        else:
            payload_item["location_name"] = request.location_name
        # Only send dates when set — omitting uses provider default (~365d).
        if date_from is not None:
            payload_item["date_from"] = date_from.isoformat()
        if date_to is not None:
            payload_item["date_to"] = date_to.isoformat()
        if request.tag:
            payload_item["tag"] = request.tag

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    self.endpoint,
                    headers=_auth_header(settings.dataforseo_login, settings.dataforseo_password),
                    content=json.dumps([payload_item]),
                )
            latency_ms = round((time.perf_counter() - started) * 1000)
            try:
                body = resp.json()
            except Exception:
                return SerpFetchResult(
                    provider=self.name,
                    http_status=resp.status_code,
                    top_status_code=None,
                    task_status_code=None,
                    task_status_message=None,
                    cost_usd=Decimal("0"),
                    snapshots=[],
                    error=f"non-JSON body ({latency_ms}ms): {resp.text[:300]}",
                )

            if not isinstance(body, dict):
                return SerpFetchResult(
                    provider=self.name,
                    http_status=resp.status_code,
                    top_status_code=None,
                    task_status_code=None,
                    task_status_message=None,
                    cost_usd=Decimal("0"),
                    snapshots=[],
                    error="response JSON is not an object",
                )

            parsed = parse_historical_response(body, self.name)
            parsed.http_status = resp.status_code
            # Surface task-level business errors clearly
            if parsed.task_status_code and parsed.task_status_code != 20000:
                parsed.error = parsed.task_status_message or f"task status {parsed.task_status_code}"
            return parsed
        except httpx.HTTPError as exc:
            return SerpFetchResult(
                provider=self.name,
                http_status=0,
                top_status_code=None,
                task_status_code=None,
                task_status_message=None,
                cost_usd=Decimal("0"),
                snapshots=[],
                error=str(exc),
            )


class DataForSeoGoogleProvider(_DataForSeoBase):
    name = "dataforseo_google_current"
    endpoint = CURRENT_URL


class DataForSeoLegacyProvider(_DataForSeoBase):
    name = "dataforseo_legacy"
    endpoint = LEGACY_URL
