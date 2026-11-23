# Historical SERP Domain Finder

Внутренний инструмент: **исторические Google SERP (DataForSEO) → unique `registrable_domain` (PSL) → WhoisFreaks availability → фильтры / экспорт**.

| Документ | Путь |
|---|---|
| ТЗ | `D:\Historical_SERP_Domain_Finder_TZ_v1_1.md` |
| Roadmap MVP | `D:\Historical_SERP_Domain_Finder_Roadmap_v1.md` |
| Архитектура | [`docs/architecture.md`](docs/architecture.md) |
| VPS / deploy | [`docs/deploy-vps.md`](docs/deploy-vps.md) |
| Секреты | [`docs/secrets.md`](docs/secrets.md) |
| Backup Postgres | [`docs/backup-postgres.md`](docs/backup-postgres.md) |
| Миграции | [`docs/migrations.md`](docs/migrations.md) |
| OpenAPI snapshot | [`docs/openapi.json`](docs/openapi.json) |
| Acceptance §14/§15.10 | [`docs/acceptance_serp_avail_checklist.md`](docs/acceptance_serp_avail_checklist.md) |
| Пилот AU+UK | [`docs/pilot_au_uk_latest.md`](docs/pilot_au_uk_latest.md) |
| Примеры raw/normalized | [`docs/examples_raw_normalized.md`](docs/examples_raw_normalized.md) · [`docs/examples/`](docs/examples/) |
| **Spike protocol (поставка)** | [`docs/spike/`](docs/spike/) · таблица истории [`docs/history_availability_table.md`](docs/history_availability_table.md) |
| **Actual cost (§17)** | [`docs/actual_cost.md`](docs/actual_cost.md) · [`docs/actual_cost_latest.json`](docs/actual_cost_latest.json) |
| **Demo E2E (§17)** | [`docs/demo_e2e_checklist.md`](docs/demo_e2e_checklist.md) · [`docs/demo_e2e_latest.md`](docs/demo_e2e_latest.md) |

## Статус MVP

| Этап | Статус |
|---|---|
| 0 Spike | **GO** (2026-11-19), история ≈ **365 дней** |
| 1a–1d Backend | готов (scaffold + live E2E) |
| 1.5 gaps | list projects, SERP retry, `auto_after_serp`, hostname export |
| 2 Frontend | SPA → `app/static`, на VPS через туннель |
| 3 QA | acceptance + AU/UK pilot + secrets/backup + этот пакет docs |

**Жёстко:** не слать `date_from` старше ~365 дней (DataForSEO → `40501`). UI/API clamp к `/api/meta/serp-window`.  
**Out of MVP:** покупка доменов, 2015–2020 без другого провайдера, GoDaddy Confirm (stub 501 до PAT).

## Стек

- **API:** FastAPI + SQLAlchemy + Alembic + Postgres 16  
- **Workers:** in-process threads (Redis зарезервирован)  
- **UI:** Vite + React → static mount  
- **Providers:** DataForSEO Labs Historical SERPs, WhoisFreaks Availability v2  

## Локальный запуск

```powershell
cd D:\Historical_SERP_Domain_Finder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # вписать ключи — см. docs/secrets.md

# опционально локальные Postgres/Redis:
docker compose up -d
# DATABASE_URL по умолчанию: postgresql+psycopg://hsdf:hsdf@127.0.0.1:5433/hsdf

alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8872
```

| Сервис | Local compose | VPS |
|---|---|---|
| App | **8872** | `127.0.0.1:8872` |
| Postgres | **5433** | `127.0.0.1:5434` (`hsdf-db`) |
| Redis | **6380** | `127.0.0.1:6381` (`hsdf-redis`) |

Compose-файлы: `docker-compose.yml` (local), `docker-compose.vps.yml` (VPS).

### Frontend

```powershell
cd frontend
npm install
npm run build          # → app/static (отдаёт тот же :8872)
npm run dev            # :5173, proxy на API :8872
```

Логин UI = HTTP Basic (`APP_BASIC_USER` / `APP_BASIC_PASSWORD`).

## API / OpenAPI

| | |
|---|---|
| Health (no auth) | `GET /health` |
| Swagger UI | `http://127.0.0.1:8872/docs` |
| OpenAPI JSON (live) | `/openapi.json` |
| Snapshot в репо | `docs/openapi.json` (37 paths на 2026-11-20) |
| SERP window | `GET /api/meta/serp-window` (Basic) |

Обновить snapshot после смены роутов:

```powershell
.\.venv\Scripts\python.exe -c "import json; from pathlib import Path; from app.main import app; Path('docs/openapi.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding='utf-8')"
```

## Миграции

См. [`docs/migrations.md`](docs/migrations.md). Кратко: `alembic upgrade head` → revisions `20261119_0001` + `20261120_0002`.

## VPS

Целевой хост и правила — **только** [`docs/deploy-vps.md`](docs/deploy-vps.md).

Публично: **https://hsdf.datamonosite.com/** (Basic auth).

```powershell
python scripts\bootstrap_vps.py      # один раз, по приказу
python scripts\sync_code_vps.py      # выкладка кода (не трогает .env)
python scripts\deploy_nginx_vps.py   # DNS + nginx + LE (idempotent)
python scripts\ssh_tunnel_8872.py    # опциональный туннель → :8872
python scripts\backup_postgres_vps.py
```

Каталог на сервере: `/opt/historical_serp_domain_finder`. **Не** смешивать с `gambling_sites_company` / Rybbit DB.

## Spike (Этап 0) — в поставке

```powershell
python spike\run_spike.py --skip-godaddy   # локальный прогон → spike/results/ (gitignore)
```

| Поставка §17 | Путь |
|---|---|
| Протокол + Go/No-go | [`docs/spike/spike_protocol_latest.md`](docs/spike/spike_protocol_latest.md) |
| JSON протокол | [`docs/spike/spike_protocol_latest.json`](docs/spike/spike_protocol_latest.json) |
| Таблица доступной истории | [`docs/history_availability_table.md`](docs/history_availability_table.md) |

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

| Набор | Путь |
|---|---|
| Acceptance contracts §14/§15.10 | `tests/test_acceptance_contracts.py` |
| **Spike fixtures (контрактные)** | `tests/test_spike_contracts.py` + `tests/fixtures/spike/` |
| PSL / keywords / retry / redact | `tests/test_domains.py` и др. |

Пилот: `scripts/pilot_au_uk_wide.py` → `docs/pilot_au_uk_latest.md`.

## Секреты

Только `.env` (gitignore). Имена — `.env.example`. Никогда не коммитить DataForSEO password, WhoisFreaks `apiKey`, GoDaddy PAT, `VPS_PW`. Подробности: [`docs/secrets.md`](docs/secrets.md).
