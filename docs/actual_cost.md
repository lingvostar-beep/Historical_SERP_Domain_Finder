# Actual cost — тестовые задания (TZ §17)

**Зафиксировано:** 2026-11-20  
**Валюта:** USD (как в ответах API `cost`) + WhoisFreaks **credits** (ref USD из конфига).  
**Секреты:** не включены. Кабинеты DataForSEO / WhoisFreaks сверять отдельно при закупке пакетов.

## Reference rates (конфиг MVP)

| Провайдер | Rate | Источник |
|---|---|---|
| DataForSEO Labs snapshot | **$0.00012** / returned snapshot | Spike 2026-11-19 + `DATAFORSEO_REFERENCE_PRICE_PER_SNAPSHOT` |
| WhoisFreaks | **1 credit / domain**; ref **$0.004 / credit** | `WHOISFREAKS_REFERENCE_USD_PER_CREDIT` (амортизация пакета; не путать с разовым cash outlay 5k/$20) |

Пустые месяцы / `40501` → DataForSEO `cost = 0` (не биллим snapshot).  
Свежий TTL-кэш WhoisFreaks → **0** новых credits.

---

## 1. Spike (2026-11-19) — feasibility

| Probe | DataForSEO `cost` |
|---|---:|
| Legacy/Current old `date_from` (40501) | 0 |
| Legacy `amazon` US nodate (5 snaps) | 0.0006 |
| Legacy `amazon` US 2026-Q1 (2 snaps) | 0.00024 |
| Legacy/Current `online casino` AU nodate (6 snaps) | **0.00072** each |
| Current `amazon` AU Sep (1 snap) | **0.00012** |

WhoisFreaks Spike batch (google / example / hsdf-spike / invalidtld): статусы OK; точный credit ledger кабинета в протокол не выгружался — модель **1 credit/domain** подтверждена документацией + MVP jobs.

Полный протокол: `docs/spike/spike_protocol_latest.md`.

---

## 2. Live E2E (VPS, до пилота AU+UK)

| Run | DataForSEO | WhoisFreaks |
|---|---:|---|
| AU-only `amazon`/`casino` Sep 2026 (E2E) | **$0.00012** (1 snap) | **6 credits** / ~$0.024 (ref) |

---

## 3. Пилот AU + UK — **канонический actual_cost для §17**

Машиночитаемо: [`actual_cost_latest.json`](actual_cost_latest.json) · детали: `docs/pilot_au_uk_latest.md`

### 3a. Narrow Sep-only (первый проход)

| | |
|---|---|
| Run | `8ed96215-5ac1-405b-8e84-d8626c234c67` |
| DataForSEO | **$0.000120** (1 snapshot; UK Sep = NO_SNAPSHOT) |
| WhoisFreaks | **0 credits** (6 domains TTL-cached) |
| Total ref | **~$0.00012** |

### 3b. Wide window (итоговый пилот) — **PASS AU+UK**

| | |
|---|---|
| Run | `b6073180-4cda-4221-abd3-eff822f69497` |
| Job | `235f2365-8bdd-4dad-b057-8257192b3b00` |
| Scope | `amazon` + `online casino` × AU+UK · `2025-11-20`→`2026-09-30` · TOP-20 |
| Snapshots saved | 26 |
| Estimate SERP (cells) | $0.005280 (≤44) |
| **DataForSEO actual** | **`$0.003120`** |
| WhoisFreaks | **25 credits** force_refresh · **`$0.100000`** ref |
| **Total ref** | **`~$0.103120`** |

---

## Сводка для сдачи

| Задание | DataForSEO USD | WhoisFreaks | Total (ref USD) |
|---|---:|---|---:|
| Spike diagnostics (сумма заметных успешных проб, ориентир) | ~0.0024+ | batch screening (см. протокол) | — |
| E2E AU | 0.00012 | 6 cr ≈ 0.024 | ≈ 0.024 |
| **Pilot AU+UK (wide)** | **0.00312** | **25 cr = 0.100** | **≈ 0.103** |

**Не обещать:** стоимость «за любой месяц 2022–2024» — на этом аккаунте такие `date_from` → `40501`, cost 0, данных нет.  
**GoDaddy Confirm:** не тарифицировался (stub / нет PAT).
