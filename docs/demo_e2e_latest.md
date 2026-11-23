# Demo E2E — SERP → domains → availability → Available → export

**Generated (UTC):** `2026-11-20T09:53:25.893569+00:00`  
**Verdict:** **PASS**  
**Run:** `ff629033-e40d-43a0-9547-94cdd2cfe18d` · **Job:** `0f40ef5c-bb94-44e4-81ec-75370f7b4f3c`  

**Note:** Available-only = 0 for amazon AU shortlist is expected (domains TAKEN). Filter + `available_domains.txt` with `# WARNING` header and zero domains still PASS.

## Steps

- **PASS** `health`
- **PASS** `project_setup`
- **PASS** `serp_run`
- **PASS** `unique_domains`
- **PASS** `availability_batch`
- **PASS** `available_filter`
- **PASS** `exports`

## Costs

| DataForSEO | `$0.000120` |
| WhoisFreaks | `6` credits / `$0.024000` |

## Checklist (TZ §17)

| Step | Result |
|---|---|
| historical SERP | PASS |
| unique domains | PASS (6) |
| batch availability | PASS (6 credits) |
| filter Available | PASS (0 available — correct for this SERP set) |
| export | PASS (SERP + availability files) |

Machine-readable: `docs/demo_e2e_latest.json`

Procedure: `docs/demo_e2e_checklist.md`
