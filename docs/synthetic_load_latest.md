# Synthetic mid-scale load — latest

**Generated:** `2026-11-23T08:51:12.603238+00:00`  
**Provider spend:** `$0` (no live SERP/availability APIs)

## Seed

| | |
|---|---|
| Project | `SYNTHETIC_LOAD_TEST_20261123T084703Z` |
| Run | `c4c9c94b-0126-4e7a-ba26-c6247f0dedc2` |
| Keywords × locs × months | 500 × 2 × 12 |
| Snapshots / results | 12000 / 120000 |
| Domain pool | 5000 |
| Insert time | 22.392s |

## Benchmark

| Call | Seconds | Notes |
|---|---:|---|
| Domains page 1 (50) | 1.706 | total=5000 |
| Domains page 2 | 1.213 | |
| Domains last page (100) | 1.249 | deep OFFSET |
| build_run_exports | 159.048 | {'unique_domains': 5000, 'unique_list_kind': 'registrable_domain', 'domain_rows': 5000, 'position_rows': 120000, 'coverage_rows': 12000} |
| Availability page 1 | 45.424 | total=5000 |
| Coverage matrix (25 kw) | 0.1 | kw_total=500 |

## Interpretation

Evidence for Stage 3 / §13 mid-scale without provider budget. If Domains last-page or export times grow steeply, prioritize precomputed domain aggregates (Roadmap 1c) and/or keyset pagination.
