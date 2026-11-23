# Secrets — Historical SERP Domain Finder

**Обновлено:** 2026-11-20  
**Правило:** секреты только в `.env` (локально / на VPS). Никогда в git, чат, Spike-экспорты, frontend, OpenAPI examples с реальными значениями.

## Инвентарь

| Secret | Где живёт | Кто использует | Можно ли во frontend |
|---|---|---|---|
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | `.env` (VPS + local) | SERP provider | **Нет** |
| `WHOISFREAKS_API_KEY` | `.env` | Availability provider (query `apiKey`) | **Нет** |
| `GODADDY_PAT` | `.env` (optional; сейчас пусто) | Confirm live | **Нет** |
| `APP_BASIC_USER` / `APP_BASIC_PASSWORD` | `.env` + копия в `deploy/vps_bootstrap_credentials.txt` (gitignored) | HTTP Basic UI/API | Пароль только в sessionStorage браузера оператора, не в репо |
| `HSDF_PG_PASSWORD` / `DATABASE_URL` | `.env` на VPS | Postgres `hsdf-db` | **Нет** |
| `VPS_PW` (SSH) | **только** company `d:\Cursor\gambling_sites_company\.env` | bootstrap / sync / backup scripts | **Нет**; не копировать в этот репо |

Имена без значений — в `.env.example`.

## Где лежат на VPS

| Путь | Содержимое |
|---|---|
| `/opt/historical_serp_domain_finder/.env` | Полный runtime env (права `600`, owner root) |
| `/opt/historical_serp_domain_finder/deploy/` | unit-файлы; **не** credentials |
| Локально `deploy/vps_bootstrap_credentials.txt` | После bootstrap: Basic + DB URL reminder — **gitignore** |

## Запреты (приёмка §15.10.11 / §13)

1. Не коммитить `.env`, `*credentials*`, сырые WhoisFreaks URL с `apiKey=`.
2. Не логировать полный URL WhoisFreaks — только через `redact_url()` / `scrub_mapping()`.
3. Не класть ключи в `data/exports/`, `spike/results/` для шаринга, frontend bundle.
4. Не использовать ключи пайплайна / Rybbit / dashboard в этом приложении.
5. Не печатать `VPS_PW`, DataForSEO password, WhoisFreaks key в ответы ассистента / тикеты.

## Ротация (оператор)

| Secret | Как ротировать |
|---|---|
| Basic auth | Сменить в VPS `.env` → `systemctl restart hsdf-api` → обновить локальный credentials-файл |
| DataForSEO | Новый пароль в кабинете → VPS `.env` → restart |
| WhoisFreaks | Новый key в кабинете → VPS `.env` → restart |
| Postgres password | Сменить `HSDF_PG_PASSWORD` + `DATABASE_URL`, пересоздать/alter user в контейнере, restart API; **сначала backup** |
| SSH `VPS_PW` | Только в company `.env`; этот репо не хранит |

## Проверка «не утекло»

```powershell
cd D:\Historical_SERP_Domain_Finder
# tracked files must not contain real keys
git ls-files | Select-String -Pattern 'credentials|\.env$'
rg -n "apiKey=|DATAFORSEO_PASSWORD=.+" --glob '!.venv/**' --glob '!frontend/node_modules/**' .
```

Ожидание: совпадения только в `.env.example` (пустые), docs (плейсхолдеры), тестах с `secret123` / redact.

## TLS / публичный доступ

API слушает **`127.0.0.1:8872`**. Снаружи: **`https://hsdf.datamonosite.com`** (nginx + Let's Encrypt, DNS-only A). Auth — app Basic; пароль в `deploy/vps_bootstrap_credentials.txt` / VPS `.env` (`BASIC_AUTH_*`). Порт `8872` в мир не открывать. SSH tunnel — запасной канал.
