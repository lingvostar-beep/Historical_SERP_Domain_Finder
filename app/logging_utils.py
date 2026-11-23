"""Safe logging helpers — never leak API secrets."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_QUERY_KEYS = {
    "apikey",
    "api_key",
    "password",
    "token",
    "access_token",
    "authorization",
}


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _SECRET_QUERY_KEYS:
            kept.append(f"{key}=***")
        else:
            kept.append(urlencode([(key, value)]))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment))


def scrub_mapping(data: dict) -> dict:
    """Shallow scrub of common secret keys for debug dumps."""
    out = {}
    for key, value in data.items():
        lk = str(key).lower()
        if lk in _SECRET_QUERY_KEYS or lk.endswith("_password") or lk.endswith("_pat"):
            out[key] = "***"
        elif isinstance(value, str) and ("apiKey=" in value or "api_key=" in value):
            out[key] = redact_url(value)
        else:
            out[key] = value
    return out
