# Historical SERP Domain Finder — agent notes

Standalone internal SEO tool. **Not** related to gambling site pipelines or other company repos — same VPS later, **separate** `/opt` tree and secrets.

## Documents

| File | Role |
|---|---|
| `D:\Historical_SERP_Domain_Finder_TZ_v1_1.md` | Full TZ (source of truth for product rules) |
| `D:\Historical_SERP_Domain_Finder_Roadmap_v1.md` | MVP roadmap + day estimates |
| `docs/deploy-vps.md` | **VPS / deploy rules** (read before any server work) |
| `docs/architecture.md` | MVP architecture + sequence diagrams |
| `docs/migrations.md` | Alembic revision index |
| `docs/openapi.json` | OpenAPI snapshot (live also `/docs`) |
| `docs/examples_raw_normalized.md` | Raw vs normalized API examples (no secrets) |
| `docs/spike/` | Spike protocol delivery (md+json+GO) |
| `docs/history_availability_table.md` | Usable history table from Spike |
| `docs/actual_cost.md` | Fixed DataForSEO + WhoisFreaks test costs |
| `docs/demo_e2e_checklist.md` | E2E demo procedure + latest result |
| `docs/secrets.md` | Secrets inventory / rotation / leak rules |
| `docs/backup-postgres.md` | `hsdf-db` dump & restore |
| `docs/spike_go_nogo_checklist.md` | Spike Go/No-go checklist |
| This repo `README.md` | How to run locally |

## Current phase

**Этап 0 Spike — DONE (2026-11-19): GO MVP with 365-day limit.**  
Protocol: `spike/results/spike_protocol_latest.md`.

**Этап 1a Foundation — DONE.**  
**Этап 1b SERP pipeline — DONE (scaffold).**  
**Этап 1c Results API + exports — DONE.**  
**Этап 1d Availability — DONE (scaffold):** WhoisFreaks batch/TTL/budget/exports; GoDaddy confirm = 501 stub.  
**Этап 1.5 gaps — DONE (2026-11-20):** live E2E VPS (`scripts/e2e_vps_pilot.py`); `GET /api/projects`; SERP retry 429/5xx; `auto_after_serp`; export `dedupe_mode=hostname`.  
**Этап 2 Frontend — DONE (scaffold):** Vite React SPA → `app/static`, served by FastAPI.  
**Этап 3 QA — IN PROGRESS:**  
- Acceptance §14+§15.10: `docs/acceptance_serp_avail_checklist.md`  
- Pilot AU+UK: `docs/pilot_au_uk_latest.md` (wide window; SERP $0.00312 + WF 25 cr / $0.10)  
**Этап 3 — docs package:** DONE.  
**Этап 3 — Spike contract tests:** DONE.  
**Этап 3 — raw/normalized examples:** DONE.  
**Этап 3 — Spike protocol in delivery:** DONE.  
**Этап 3 — actual_cost:** DONE.  
**Этап 3 — Demo E2E:** DONE (`docs/demo_e2e_latest.md` — PASS SERP→domains→avail→Available→export).  
**Этап 3 QA:** essentially complete for roadmap items 1–9.  
**Public nginx + TLS:** DONE (2026-11-20) — `https://hsdf.datamonosite.com` → `:8872`.

### Hard product constraints from Spike (do not regress)

- DataForSEO historical window ≈ **last 365 days only**. Old `date_from` (2022–2024) → task `40501`.
- Do not advertise 2021–2024 history in UI on this provider.
- Primary SERP: `dataforseo_google_current` (Legacy optional; same window observed).
- WhoisFreaks primary availability; enums seen: `AVAILABLE` / `UNAVAILABLE` / `UNKNOWN`.
- GoDaddy confirm deferred until PAT exists.
- Reference SERP cost ≈ `$0.00012` per returned snapshot.

## Hosting (do not forget in long chats)

Canonical detail: **`docs/deploy-vps.md`**.

- Production target: dashboard VPS **`89.163.221.244`** (Ubuntu, Docker already on server).
- Install path: **`/opt/historical_serp_domain_finder`** — never inside `gambling_sites_company`.
- Own Postgres/Redis for this app; **do not** reuse Rybbit DB on `:5432`/`:6379`.
- App listen port: **`8872`** (not `8870` — that is plan_board).
- Public URL: **`https://hsdf.datamonosite.com`** (nginx + LE; Basic auth). Redeploy vhost: `python scripts/deploy_nginx_vps.py`.
- Local Docker on the operator’s Windows PC is **optional**; deploy uses VPS Docker.
- Bootstrap on VPS is allowed when the operator orders it (`python scripts/bootstrap_vps.py`).
- Credentials after bootstrap: local `deploy/vps_bootstrap_credentials.txt` (gitignored).

## MVP in / out (short)

**In:** historical SERP (DataForSEO) → unique `registrable_domain` (PSL) → WhoisFreaks availability (+ GoDaddy confirm if available) → filters/exports.

**Out:** domain purchase, traffic/Wayback, related keywords, 2015–2020 without proven source, HTTP-as-availability, Phase 2 extras.

## Secrets

- Only in `.env` (gitignored). Names in `.env.example`.
- Never print DataForSEO password, WhoisFreaks `apiKey`, or GoDaddy PAT in logs, commits, or spike exports that get shared.
- VPS SSH password lives in **company** `.env` as `VPS_PW` — use only for ops probes/deploy; never commit or paste into this repo.

## Billing / models

Prefer Auto / subscription models for this project. Avoid spending “Other models” quota unless the operator asks.
