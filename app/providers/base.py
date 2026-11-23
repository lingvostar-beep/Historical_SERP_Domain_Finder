from __future__ import annotations

from typing import Protocol

from app.config import get_settings
from app.providers.dataforseo import DataForSeoGoogleProvider, DataForSeoLegacyProvider
from app.providers.types import SerpFetchRequest, SerpFetchResult


class HistoricalSerpProvider(Protocol):
    name: str

    def fetch(self, request: SerpFetchRequest) -> SerpFetchResult: ...


def get_serp_provider(source: str | None = None) -> HistoricalSerpProvider:
    settings = get_settings()
    key = (source or settings.dataforseo_primary_source).strip().lower()
    if key in {"dataforseo_legacy", "legacy"}:
        return DataForSeoLegacyProvider()
    if key in {"dataforseo_google_current", "current", "google"}:
        return DataForSeoGoogleProvider()
    raise ValueError(f"Unknown SERP source: {source!r}")
