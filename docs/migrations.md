# SQL migrations (Alembic)

**Head:** `20261123_0003`  
**Команда:** `alembic upgrade head` (локально или на VPS после sync).

## Цепочка

| Revision | File | Содержание |
|---|---|---|
| `20261119_0001` | `alembic/versions/20261119_0001_initial_serp_schema.py` | TZ §7 SERP core |
| `20261120_0002` | `alembic/versions/20261120_0002_availability.py` | TZ §15 availability + TLD policy seed |
| `20261123_0003` | `alembic/versions/20261123_0003_snapshot_run_isolation.py` | `serp_snapshots.run_id` + per-run unique (no cross-run theft) |

## Таблицы по ревизиям

### 0001 — SERP

`projects`, `keywords`, `project_keywords`, `project_targets`, `runs`, `run_queries`, `serp_snapshots`, `serp_results`, `coverage`, `api_usage`

### 0002 — Availability

`domain_registry_checks`, `domain_availability_state`, `availability_jobs`, `availability_job_items`, `availability_provider_usage`, `tld_registration_policies`  
(+ seed: `com.au` / `net.au` / `co.uk` / … → `REQUIRES_EVIDENCE`)

### 0003 — Snapshot run isolation

`serp_snapshots.run_id` (FK → `runs`, backfill from `run_queries`); drop global `uq_provider_snapshot`; add `uq_run_provider_snapshot (run_id, provider, keyword_id, location_code, language_code, observed_at)`.

## Практика

```powershell
# статус
alembic current
alembic history

# применить
alembic upgrade head
```

На VPS sync уже вызывает `alembic upgrade head` перед restart API.  
Новые изменения схемы — только через новую revision, не руками в проде без backup (`docs/backup-postgres.md`).
