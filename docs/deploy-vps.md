# Deploy / VPS notes (Historical SERP Domain Finder)

**Проверено:** 2026-11-19 (SSH probe); **дополнено** 2026-11-20 (secrets / backup / sync / public nginx).  
**Назначение:** куда едет продукт, чего не трогать, как обновлять код и бэкапить БД.

Связанные доки:

| Документ | Тема |
|---|---|
| `docs/architecture.md` | Архитектура MVP |
| `docs/migrations.md` / `docs/openapi.json` | Схема БД / API snapshot |
| `docs/secrets.md` | Инвентарь секретов, ротация, запреты утечек |
| `docs/backup-postgres.md` | `pg_dump` / restore для `hsdf-db` |
| `docs/acceptance_serp_avail_checklist.md` | QA §14 / §15.10 |
| `docs/pilot_au_uk_latest.md` | Пилот AU+UK + actual cost |

## Продакшен-хост

Тот же VPS, где уже живут company dashboard / sandbox / Rybbit / plan board:

| | |
|---|---|
| Host | `89.163.221.244` (`vps2656383`) |
| OS | Ubuntu 24.04 LTS |
| SSH | `root` + `VPS_PW` из **company** `.env` (`d:\Cursor\gambling_sites_company\.env`) — не коммитить, не светить в чат |
| Ресурсы (на дату проверки) | 6 CPU, ~15 GiB RAM (~12 GiB available), ~127 GiB free disk — запас есть |
| Docker на VPS | **есть** (Docker 29.x + Compose) |

Локальный Docker на Windows **не обязателен**: разработка на ПК, БД/рантайм на VPS при деплое.

## Куда класть этот продукт

| Правило | Деталь |
|---|---|
| Каталог | **`/opt/historical_serp_domain_finder`** (отдельное дерево) |
| Не класть | внутрь `/opt/gambling_sites_company` или sandbox |
| Не смешивать | `.env`, users, CSV брендов, Claude keys пайплайна |
| Свой Postgres/Redis | отдельный docker compose **этого** проекта (или отдельная БД) |
| Не использовать | Rybbit `postgres` / `redis` на `127.0.0.1:5432` / `:6379` |

## Порты (занято на VPS — не занимать)

| Порт | Кто |
|---|---|
| `8865` | company-dashboard |
| `8866` | company-dashboard-sandbox |
| **`8870`** | **plan_board** (`/opt/plan_board`) — **запрещён для HSDF** |
| `8871` | другой python на хосте |
| `5432` / `6379` | Rybbit docker postgres/redis (localhost only) |
| `3001` / `3002` | Rybbit backend/client |
| `80` / `443` | nginx |

**Порт приложения HSDF:** `8872` (localhost) + nginx `hsdf.datamonosite.com` → TLS.

Локально на Windows тоже лучше `APP_PORT=8872`, чтобы не путать с plan board.

## Bootstrap (dev на VPS)

По приказу оператора (2026-11-19) разрешён **bootstrap** для отладки 1b+ без локального Docker:

```powershell
cd D:\Historical_SERP_Domain_Finder
python scripts\bootstrap_vps.py
```

- Каталог: `/opt/historical_serp_domain_finder`
- Compose: `docker-compose.vps.yml` → Postgres `127.0.0.1:5434`, Redis `127.0.0.1:6381`
- API: systemd `hsdf-api.service` → `127.0.0.1:8872`
- Логин Basic: см. локальный `deploy/vps_bootstrap_credentials.txt` (gitignore)
- Публично: **https://hsdf.datamonosite.com/** (Basic auth как на API)
- Туннель с ПК (опционально): `ssh -L 8872:127.0.0.1:8872 root@89.163.221.244` → http://127.0.0.1:8872/docs

**Не** трогать dashboard/Rybbit compose при деплое HSDF.

## Обновление кода (после bootstrap)

На ПК оператора (нужен `VPS_PW` в company `.env`):

```powershell
cd D:\Historical_SERP_Domain_Finder
# если менялся frontend:
cd frontend; npm run build; cd ..
python scripts\sync_code_vps.py
```

`sync_code_vps.py`:

- заливает дерево **без** `.env`, `node_modules`, credentials, `spike/results`, runtime `data/`;
- на сервере: `alembic upgrade head` + `systemctl restart hsdf-api`;
- **не** перезаписывает VPS `.env` и Docker volumes.

Проверка:

```powershell
python scripts\ssh_tunnel_8872.py   # если туннеля ещё нет
# http://127.0.0.1:8872/          UI
# http://127.0.0.1:8872/health    без auth
# http://127.0.0.1:8872/docs      OpenAPI
```

## Сервисы на VPS (чеклист)

| Компонент | Как проверить |
|---|---|
| API | `systemctl status hsdf-api` · `curl -sS http://127.0.0.1:8872/health` |
| Postgres | `docker exec hsdf-db pg_isready -U hsdf -d hsdf` · порт только `127.0.0.1:5434` |
| Redis | `docker exec hsdf-redis redis-cli ping` · `127.0.0.1:6381` |
| Логи API | `journalctl -u hsdf-api -n 100 --no-pager` (не должно быть `apiKey=` plaintext) |

## Secrets / backup (кратко)

- Полный инвентарь: **`docs/secrets.md`**
- Бэкап БД: **`docs/backup-postgres.md`** · `python scripts\backup_postgres_vps.py` · опция `--pull`
- Дампы: `/opt/historical_serp_domain_finder/backups/` (и локальный `backups/` при `--pull`, gitignore)

## TLS / nginx

| | |
|---|---|
| Hostname | **`hsdf.datamonosite.com`** |
| DNS | A → `89.163.221.244`, zone `datamonosite.com`, **DNS only** (не proxied) |
| TLS | Let's Encrypt (`/etc/letsencrypt/live/hsdf.datamonosite.com/`) |
| nginx | sites-available/enabled `hsdf.datamonosite.com` → `http://127.0.0.1:8872` |
| Auth | app Basic (как раньше); порт `8872` наружу не открыт |
| SEO | `X-Robots-Tag: noindex…`, `robots.txt` Disallow |
| Deploy | `python scripts/deploy_nginx_vps.py` (idempotent; `--nginx-only` без DNS) |

Не занимать default `server_name _` (IP dashboard) и чужие vhost (`plan` / `domains` / `sandbox` / `rybbit`).

## Связь с другими репо

- Этот продукт: `D:\Historical_SERP_Domain_Finder`
- Пайплайн/дашборд: `d:\Cursor\gambling_sites_company` — только сосед по железу, не по коду
