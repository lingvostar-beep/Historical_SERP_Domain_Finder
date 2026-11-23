"""URL / hostname / registrable_domain via Public Suffix List — TZ §6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import tldextract

# ICANN-only: do not treat private suffixes (blogspot.com, github.io) as registrable eTLD+1
_EXTRACT = tldextract.TLDExtract(include_psl_private_domains=False)


@dataclass
class DomainParts:
    url: Optional[str]
    hostname: Optional[str]
    registrable_domain: Optional[str]
    provider_domain: Optional[str]
    subdomain: Optional[str]
    is_platform_host: bool
    parse_error: Optional[str] = None


_PLATFORM_SUFFIXES = (
    "blogspot.com",
    "github.io",
    "herokuapp.com",
    "netlify.app",
    "vercel.app",
    "workers.dev",
    "pages.dev",
)


def normalize_hostname(host: str) -> str:
    h = host.strip().rstrip(".").lower()
    if h.startswith("www."):
        # keep www in hostname field? TZ: hostname lowercase; registrable drops www via PSL
        pass
    return h


def classify_registrable_domain(domain: str) -> tuple[Optional[str], Optional[str]]:
    """TZ §15.5/§15.6 — pre-flight before availability API.

    Returns ``(status, error_code)`` when the name must not be billed/checked:
    ``INVALID`` / ``UNSUPPORTED_TLD``. Returns ``(None, None)`` when OK to query.
    """
    d = (domain or "").strip().lower().rstrip(".")
    if not d or "://" in d or "/" in d or " " in d or d.startswith(".") or "." not in d:
        return "INVALID", "malformed_domain"
    labels = d.split(".")
    if any(not lab or len(lab) > 63 or lab.startswith("-") or lab.endswith("-") for lab in labels):
        return "INVALID", "malformed_label"
    if any(not all(c.isalnum() or c == "-" for c in lab) for lab in labels):
        return "INVALID", "malformed_label"

    ext = _EXTRACT(d)
    if ext.suffix and not ext.domain:
        return "INVALID", "public_suffix_only"
    if not ext.suffix:
        return "UNSUPPORTED_TLD", "unrecognized_tld"
    # Suffix present but not a real registrable eTLD+1 (provider often returns UNKNOWN)
    if not ext.domain:
        return "INVALID", "public_suffix_only"
    return None, None


def parse_result_url(url: Optional[str], provider_domain: Optional[str] = None) -> DomainParts:
    if not url and not provider_domain:
        return DomainParts(None, None, None, None, None, False, "missing url and domain")

    raw_url = url
    host = None
    err = None
    if url:
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = parsed.hostname
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
    if not host and provider_domain:
        host = provider_domain

    if not host:
        return DomainParts(raw_url, None, None, provider_domain, None, False, err or "no hostname")

    host = normalize_hostname(host)
    ext = _EXTRACT(host)
    registrable = None
    subdomain = ext.subdomain or None
    if ext.domain and ext.suffix:
        registrable = f"{ext.domain}.{ext.suffix}".lower()
    elif ext.suffix and not ext.domain:
        # bare public suffix — not registrable
        registrable = None
        err = err or "public_suffix_only"
    else:
        registrable = host

    is_platform = any(host == s or host.endswith("." + s) for s in _PLATFORM_SUFFIXES)
    # Also flag if registrable itself is a known platform apex we still want tagged
    if registrable and registrable in _PLATFORM_SUFFIXES:
        is_platform = True

    return DomainParts(
        url=raw_url,
        hostname=host,
        registrable_domain=registrable,
        provider_domain=provider_domain.lower() if provider_domain else None,
        subdomain=subdomain,
        is_platform_host=is_platform,
        parse_error=err,
    )
