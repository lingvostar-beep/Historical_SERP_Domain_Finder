# Pilot AU + UK — 2026-11-20

**Generated (UTC):** `2026-11-20T09:07:02.093346+00:00`  
**Final run (wide window):** `b6073180-4cda-4221-abd3-eff822f69497` · job `235f2365-8bdd-4dad-b057-8257192b3b00`

## Scope

| | |
|---|---|
| Keywords | `amazon`, `online casino` |
| Geos | Australia `2036` + United Kingdom `2826` (en) |
| Period | **`2025-11-20` → `2026-09-30`** (full Spike-allowed window; Sep-only UK was empty) |
| Depth | TOP-20 |
| Availability | max 25 domains, **force_refresh** |

## Costs (actual)

Каноническая фиксация для §17: **`docs/actual_cost.md`** / `docs/actual_cost_latest.json`.

| Provider | Spend |
|---|---|
| DataForSEO | **$0.003120** |
| WhoisFreaks | **25 credits** / **$0.100000** |
| **Total (ref)** | **~$0.103120** |

SERP estimate beforehand: `$0.005280` (≤44 planned cells; billable = returned snapshots).

## Multigeo proof

| Geo | Has snapshot data | Distinct domains (positions) | Coverage statuses |
|---|---|---|---|
| AU 2036 | **True** | 92 | `{"NO_SNAPSHOT": 10, "AVAILABLE": 10, "PARTIAL_DEPTH": 2}` |
| UK 2826 | **True** | 89 | `{"AVAILABLE": 12, "NO_SNAPSHOT": 8, "PARTIAL_DEPTH": 2}` |

| Metric | Value |
|---|---|
| Queries | 4 COMPLETED (`amazon`/`online casino` × AU/UK) |
| Snapshots saved | 26 |
| Unique registrable domains | 158 |
| Positions | 481 |
| Availability rows | 158 |
| Available-only | 0 |

## Narrow Sep-2026 pass (first attempt)

- 4 queries COMPLETED, **1** snapshot (AU `amazon` only).
- UK Sep cells = `NO_SNAPSHOT` (archive gap, not API failure).
- WhoisFreaks **0 credits** (all 6 domains TTL-cached from earlier E2E).
- Cost: **$0.000120** SERP.

## Exports

- SERP: `95a6baa3-b14f-4bc0-9f2d-c375a02d7976`
- Availability: `fa5ab106-1bc5-4c59-8023-b3ab7c4b3bb8`

## Verdict

- **PASS** multigeo pipeline (AU+UK matrix, coverage, exports).
- UK data requires a **wider date window** than Sep-2026 alone for these keywords on this account.
- Actual spend stayed well under the agreed **$0.05–0.17** band.
- Details: `docs/pilot_au_uk_latest.json`
