# SQL migrations (Alembic)

**Head:** `20261120_0002`  
**Команда:** `alembic upgrade head` (локально или на VPS после sync).

## Цепочка

| Revision | File | Содержание |
|---|---|---|
| `20261119_0001` | `alembic/versions/20261119_0001_initial_serp_schema.py` | TZ §7 SERP core |
| `20261120_0002` | `alembic/versions/20261120_0002_availability.py` | TZ §15 availability + TLD policy seed |

## Таблицы по ревизиям

### 0001 — SERP

`projects`, `keywords`, `project_keywords`, `project_targets`, `runs`, `run_queries`, `serp_snapshots`, `serp_results`, `coverage`, `api_usage`

### 0002 — Availability

`domain_registry_checks`, `domain_availability_state`, `availability_jobs`, `availability_job_items`, `availability_provider_usage`, `tld_registration_policies`  
(+ seed: `com.au` / `net.au` / `co.uk` / … → `REQUIRES_EVIDENCE`)

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
