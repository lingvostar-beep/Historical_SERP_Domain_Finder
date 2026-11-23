"""DataForSEO locations_and_languages catalog with file cache ≥24h."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import get_settings

LOCATIONS_URL = "https://api.dataforseo.com/v3/dataforseo_labs/locations_and_languages"


@dataclass
class LocationLanguage:
    location_code: int
    location_name: str
    location_code_parent: Optional[int]
    country_iso_code: Optional[str]
    location_type: Optional[str]
    languages: list[dict[str, Any]]


class LocationsService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _cache_path(self) -> Path:
        path = self.settings.locations_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _cache_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age_h = (time.time() - path.stat().st_mtime) / 3600
        return age_h <= self.settings.locations_cache_ttl_hours

    def _load_cache(self) -> Optional[dict[str, Any]]:
        path = self._cache_path()
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_cache(self, payload: dict[str, Any]) -> None:
        path = self._cache_path()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def fetch_remote(self) -> dict[str, Any]:
        settings = self.settings
        if not settings.dataforseo_login or not settings.dataforseo_password:
            raise RuntimeError("DATAFORSEO_LOGIN/PASSWORD required to refresh locations")

        import base64

        token = base64.b64encode(
            f"{settings.dataforseo_login}:{settings.dataforseo_password}".encode()
        ).decode("ascii")
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(
                LOCATIONS_URL,
                headers={"Authorization": f"Basic {token}"},
            )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise RuntimeError("locations response is not an object")
        tasks = body.get("tasks") or []
        task = tasks[0] if tasks else {}
        if task.get("status_code") not in (None, 20000):
            raise RuntimeError(f"locations task error: {task.get('status_code')} {task.get('status_message')}")
        items = []
        for res in task.get("result") or []:
            if isinstance(res, dict) and "location_code" in res:
                items.append(res)
            elif isinstance(res, list):
                items.extend([x for x in res if isinstance(x, dict)])
        # Some DFS responses nest result as list of location objects directly
        if not items and isinstance(task.get("result"), list):
            items = [x for x in task["result"] if isinstance(x, dict) and "location_code" in x]

        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": LOCATIONS_URL,
            "items": items,
            "raw_top_status": body.get("status_code"),
        }
        self._save_cache(payload)
        return payload

    def get_catalog(self, *, force_refresh: bool = False) -> dict[str, Any]:
        path = self._cache_path()
        if not force_refresh and self._cache_fresh(path):
            cached = self._load_cache()
            if cached:
                return cached
        return self.fetch_remote()

    def list_locations(self, *, q: str | None = None, force_refresh: bool = False) -> list[LocationLanguage]:
        catalog = self.get_catalog(force_refresh=force_refresh)
        out: list[LocationLanguage] = []
        needle = (q or "").strip().lower()
        for item in catalog.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("location_name") or "")
            if needle and needle not in name.lower():
                continue
            langs = item.get("available_languages") or item.get("languages") or []
            if not isinstance(langs, list):
                langs = []
            out.append(
                LocationLanguage(
                    location_code=int(item["location_code"]),
                    location_name=name,
                    location_code_parent=item.get("location_code_parent"),
                    country_iso_code=item.get("country_iso_code"),
                    location_type=item.get("location_type"),
                    languages=langs,
                )
            )
        return out

    def validate_pair(self, location_code: int, language_code: str) -> bool:
        for loc in self.list_locations():
            if loc.location_code != location_code:
                continue
            for lang in loc.languages:
                code = lang.get("language_code") or lang.get("code")
                if code and str(code).lower() == language_code.lower():
                    return True
            # If provider lists no languages, allow language_code (edge case)
            if not loc.languages:
                return True
        return False
