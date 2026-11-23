# Примеры сырого и нормализованного ответа (без секретов)

**Дата:** 2026-11-20  
**Источник:** Spike 2026-11-19 + committed fixtures `tests/fixtures/spike/`  
**Правило:** в примерах нет DataForSEO password, WhoisFreaks `apiKey`, Basic auth, `VPS_PW`.

Файлы лежат в [`docs/examples/`](examples/).

## 1. DataForSEO — успешный historical SERP

| | |
|---|---|
| Кейс | Current Google · keyword `amazon` · Australia · Sep 2026 |
| Raw excerpt | [`examples/raw_dataforseo_amazon_au_sep_excerpt.json`](examples/raw_dataforseo_amazon_au_sep_excerpt.json) |
| Normalized | [`examples/normalized_serp_amazon_au_sep.json`](examples/normalized_serp_amazon_au_sep.json) |

**Что важно в нормализации**

- `observed_at` / `observed_month` берутся из `datetime` снимка, не из `date_from` запроса.
- В organic попадают только `type == "organic"` (`rank_group` для TOP-N).
- URL → `hostname` + **`registrable_domain`** через PSL (`www.amazon.com.au` → `amazon.com.au`).
- `cost` провайдера → `cost_usd` (здесь `$0.00012`).

## 2. DataForSEO — ошибка старого периода (40501)

| | |
|---|---|
| Кейс | Legacy · AU · `date_from` в 2022 |
| Raw excerpt | [`examples/raw_dataforseo_task_40501_excerpt.json`](examples/raw_dataforseo_task_40501_excerpt.json) |
| Normalized | [`examples/normalized_serp_task_40501.json`](examples/normalized_serp_task_40501.json) |

Верхний `status_code` может быть `20000`, но **task** = `40501 Invalid Field: 'date_from'`.  
В приложении это **не** успешная загрузка: query `FAILED`, coverage `API_ERROR` / пустые snapshots, без ретрая (бизнес-ошибка).

## 3. WhoisFreaks — bulk availability

| | |
|---|---|
| Raw | [`examples/raw_whoisfreaks_bulk_excerpt.json`](examples/raw_whoisfreaks_bulk_excerpt.json) |
| Normalized | [`examples/normalized_availability_whoisfreaks.json`](examples/normalized_availability_whoisfreaks.json) |

| Provider `availability` | Internal status (§15.6) |
|---|---|
| `AVAILABLE` | `AVAILABLE_PRELIMINARY` |
| `UNAVAILABLE` | `TAKEN` |
| `UNKNOWN` | `UNKNOWN` |

`example.com.au` при `TAKEN`/`AVAILABLE` всё равно несёт отдельный **eligibility** флаг policy (`REQUIRES_EVIDENCE`) — это не смешивается со статусом регистрации.

Запрос к API на backend:  
`POST …/domain/availability?apiKey=***` — в логах только redacted URL (`apiKey=***`).

## 4. Как воспроизвести

```powershell
# контракты на полных фикстурах
.\.venv\Scripts\python.exe -m pytest tests\test_spike_contracts.py -q
```

Полные сырые тела (крупнее excerpts) — в `tests/fixtures/spike/` и локально в `spike/results/` (gitignore).
