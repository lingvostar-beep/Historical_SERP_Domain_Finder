# Spike protocol — Historical SERP Domain Finder

- Generated (UTC): `2026-11-19T11:47:32+00:00` (initial run) + diagnostics same day
- Keyword (TZ baseline): `online casino`
- Decision date: **2026-11-19**

## DataForSEO — initial TZ matrix (with explicit old `date_from`)

| Label | HTTP | Top status | Task status(es) | Snapshots | Organic (sum) | Cost | Error |
|---|---:|---:|---|---:|---:|---:|---|
| legacy\|AU\|2022-05 | 200 | 20000 | **40501** | 0 | 0 | 0 | Invalid Field: `date_from` |
| legacy\|AU\|2023-05 | 200 | 20000 | **40501** | 0 | 0 | 0 | Invalid Field: `date_from` |
| legacy\|AU\|2024-05 | 200 | 20000 | **40501** | 0 | 0 | 0 | Invalid Field: `date_from` |
| legacy\|AU\|recent_le365 (Oct 2026) | 200 | 20000 | 20000 | 0 | 0 | 0 | empty items (narrow month + sparse archive) |
| current\|AU\|recent_le365 | 200 | 20000 | 20000 | 0 | 0 | 0 | empty items |
| legacy\|UK\|2023-05 | 200 | 20000 | **40501** | 0 | 0 | 0 | Invalid Field: `date_from` |
| current\|AU\|2022-05 | 200 | 20000 | **40501** | 0 | 0 | 0 | Invalid Field: `date_from` |

Cabinet logs on 19.11.2026 show the same `40501 Invalid Field: 'date_from'` for those calls.

## DataForSEO — diagnostics (same account, same day)

| Probe | Task | Cost | Snapshots / notes |
|---|---|---:|---|
| Legacy `amazon` US, **no dates** | 20000 | 0.0006 | 5 snaps; organic up to ~81 |
| Legacy `amazon` US, `date_from=2024-01-01` | **40501** | 0 | old `date_from` rejected |
| Legacy `amazon` US, `2026-01-01`…`2026-03-31` | 20000 | 0.00024 | 2 snaps inside ~365d window |
| Legacy `online casino` AU, **no dates** | 20000 | 0.00072 | **6 snaps** Nov 2025 → Aug 2026 |
| Current `online casino` AU, **no dates** | 20000 | 0.00072 | **same 6 datetimes** as Legacy |
| Current `amazon` AU Sep 2026 | 20000 | 0.00012 | 1 snap; organic 6 (PARTIAL_DEPTH) |

### Organic depth (`online casino` × Australia, no dates)

| datetime (UTC) | organic |
|---|---:|
| 2025-11-29 | 100 |
| 2026-01-10 | 100 |
| 2026-02-21 | 100 |
| 2026-04-04 | 50 |
| 2026-05-17 | 40 |
| 2026-08-10 | 27 |

Reference rate observed: **~$0.00012 per returned SERP snapshot** (matches TZ public example).

**Conclusion on history depth:** this account/endpoints do **not** deliver usable 2021–2024 month picks via `date_from`. Effective archive ≈ **last ~365 days**. Legacy and Current behave equivalently for the probed casino AU case when dates are omitted.

## WhoisFreaks

- HTTP: `206`
- Endpoint (redacted): `https://api.whoisfreaks.com/v2.0/domain/availability?apiKey=***`
- `google.com` → `UNAVAILABLE`
- `example.com` → `UNAVAILABLE`
- `example.com.au` → `UNAVAILABLE`
- `hsdf-spike-*.com` → `AVAILABLE`
- `*.invalidtld` → `UNKNOWN`

Enums to freeze in MVP: at least `AVAILABLE`, `UNAVAILABLE`, `UNKNOWN`.

## GoDaddy

_skipped — `GODADDY_PAT` not configured. MVP mass screening = WhoisFreaks; Confirm live deferred._

## Go / No-go — SIGNED 2026-11-19

- [x] Legacy/Current **do not** provide usable 2022–2024 month queries (`40501` on old `date_from`)
- [x] Usable history ≈ **last 365 days** (GO with this limit)
- [x] Organic depth: often enough for TOP-100 on head terms; newer snaps may be PARTIAL_DEPTH
- [x] WhoisFreaks statuses OK for MVP primary availability
- [x] GoDaddy explicitly **deferred** (not a blocker)
- [x] **Decision:** primary SERP source = `dataforseo_google_current` (Legacy optional alias; same window for now)
- [x] **Decision:** UI date range = **only within last ~365 days**; never advertise 2021–2024 on this provider
- [x] **GO MVP** under the 365-day constraint
- [ ] Deep history 2021–2024 / 2015–2020 → **Phase 2 other provider only** (out of MVP)

## Notes

- First spike script used TZ month matrix with old `date_from` → cabinet `40501` noise; diagnostics without old dates prove the product still works for ~1 year.
- Empty Oct-2026-only window for casino AU ≠ “API dead”; use wider recent range or omit dates and filter by `datetime`.
- Do not promise “disappeared since 2022” narratives in MVP UI.
