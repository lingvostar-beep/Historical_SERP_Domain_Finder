# Postgres backup / restore — HSDF

**Обновлено:** 2026-11-20  
**БД:** только контейнер **`hsdf-db`** (compose `docker-compose.vps.yml`).  
**Не трогать:** Rybbit Postgres на `:5432`.

| | |
|---|---|
| Container | `hsdf-db` |
| DB / user | `hsdf` / `hsdf` |
| Host bind | `127.0.0.1:5434` → container `5432` |
| Volume | Docker volume `hsdf_pgdata` |
| Backup dir on VPS | `/opt/historical_serp_domain_finder/backups/` |

Пароль — из VPS `.env` (`HSDF_PG_PASSWORD` / `DATABASE_URL`). Не коммитить дампы с продовыми данными в git (папка `backups/` в `.gitignore`).

## Рекомендуемый ритм

| Когда | Что |
|---|---|
| Перед миграцией / сменой PG password / опасным SQL | ручной dump |
| Еженедельно (пока нет cron) | `python scripts/backup_postgres_vps.py` с ПК оператора |
| После крупного пилота | dump + убедиться что файл > 0 |

Авто-cron на VPS можно добавить позже (`0 3 * * 0` → тот же `pg_dump` в `backups/`).

## Быстрый backup (с ПК)

```powershell
cd D:\Historical_SERP_Domain_Finder
python scripts\backup_postgres_vps.py
```

Скрипт по SSH:

1. `docker exec hsdf-db pg_dump -U hsdf -d hsdf -Fc` →  
   `/opt/historical_serp_domain_finder/backups/hsdf_YYYYMMDD_HHMMSS.dump`
2. Печатает remote path + size (без пароля).
3. Опционально: `--pull` скачивает дамп в локальный `backups/` (gitignore).

## Backup вручную на VPS

```bash
cd /opt/historical_serp_domain_finder
mkdir -p backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec hsdf-db pg_dump -U hsdf -d hsdf -Fc -f /tmp/hsdf.dump
docker cp hsdf-db:/tmp/hsdf.dump "backups/hsdf_${STAMP}.dump"
docker exec hsdf-db rm -f /tmp/hsdf.dump
ls -lh backups/hsdf_${STAMP}.dump
```

`-Fc` = custom format (удобно для `pg_restore`). Для plain SQL: `-Fp` → `.sql`.

## Что ещё имеет смысл копировать (не Postgres)

| Путь | Зачем |
|---|---|
| `/opt/.../data/raw/` | сырые SERP/availability JSON |
| `/opt/.../data/exports/` | выгрузки пользователю |
| `/opt/.../.env` | **отдельно**, encrypted/offline; не класть рядом с публичными бэкапами без шифрования |

Volume snapshot (опционально):

```bash
docker run --rm -v hsdf_pgdata:/data -v /opt/historical_serp_domain_finder/backups:/bak alpine \
  tar czf /bak/hsdf_pgdata_${STAMP}.tgz -C /data .
```

Предпочитать `pg_dump` для логической целостности.

## Restore (осторожно — затирает данные)

1. Остановить API: `systemctl stop hsdf-api`
2. Restore в пустую/целевую БД:

```bash
# пример: пересоздать объекты из custom dump
docker exec -i hsdf-db pg_restore -U hsdf -d hsdf --clean --if-exists < backups/hsdf_YYYYMMDD.dump
# или:
docker cp backups/hsdf_YYYYMMDD.dump hsdf-db:/tmp/hsdf.dump
docker exec hsdf-db pg_restore -U hsdf -d hsdf --clean --if-exists /tmp/hsdf.dump
```

3. `cd /opt/historical_serp_domain_finder && .venv/bin/alembic upgrade head`
4. `systemctl start hsdf-api`
5. Проверка: `curl -sS http://127.0.0.1:8872/api/health/db` (с Basic).

**Не** восстанавливать дамп HSDF в Rybbit/`gambling_sites_company` БД.

## Проверка после backup

- Файл существует, размер > 1 KB (пустая схема тоже обычно больше).
- `pg_restore -l backups/….dump | head` показывает TOC.
- Секреты не попали в имя файла / чат.
