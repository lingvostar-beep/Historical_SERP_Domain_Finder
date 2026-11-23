# Таблица доступной истории (Spike 2026-11-19)

Источник: [`docs/spike/spike_protocol_latest.md`](spike/spike_protocol_latest.md).  
Аккаунт DataForSEO Labs на дату Spike.

## Запросы с явным старым `date_from` (TZ-матрица)

| Провайдер | Geo | Период | Task | Snapshots | Вывод |
|---|---|---|---|---:|---|
| Legacy | AU | 2022-05 | **40501** | 0 | старый `date_from` отклонён |
| Legacy | AU | 2023-05 | **40501** | 0 | то же |
| Legacy | AU | 2024-05 | **40501** | 0 | то же |
| Legacy | UK | 2023-05 | **40501** | 0 | то же |
| Current | AU | 2022-05 | **40501** | 0 | то же |
| Legacy / Current | AU | «recent» узкий Oct-2026 | 20000 | 0 | пустой месяц ≠ API мёртв |

## Рабочие пробы (без старых дат / внутри ~365d)

| Провайдер | Запрос | Task | Cost | Snapshots |
|---|---|---|---:|---:|
| Legacy | `amazon` US, без дат | 20000 | 0.0006 | 5 |
| Legacy | `amazon` US, `date_from=2024-01-01` | **40501** | 0 | 0 |
| Legacy | `amazon` US, 2026-Q1 | 20000 | 0.00024 | 2 |
| Legacy | `online casino` AU, без дат | 20000 | 0.00072 | **6** (Nov 2025→Aug 2026) |
| Current | `online casino` AU, без дат | 20000 | 0.00072 | **те же 6 datetime** |
| Current | `amazon` AU Sep 2026 | 20000 | 0.00012 | 1 (organic 6, PARTIAL_DEPTH) |

### Organic depth — `online casino` × AU (no dates)

| datetime (UTC) | organic |
|---|---:|
| 2025-11-29 | 100 |
| 2026-01-10 | 100 |
| 2026-02-21 | 100 |
| 2026-04-04 | 50 |
| 2026-05-17 | 40 |
| 2026-08-10 | 27 |

## Итог для продукта

| Параметр | Значение |
|---|---|
| Usable history | ≈ **last 365 days** |
| UI / API clamp | `DATAFORSEO_MAX_HISTORY_DAYS=365` · `/api/meta/serp-window` |
| Primary source | `dataforseo_google_current` |
| 2021–2024 month picks | **недоступны** на этом аккаунте (`40501`) → не рекламировать |
| Reference SERP price | ~**$0.00012** / returned snapshot |
| Phase 2 | другой провайдер для 2015–2020 / глубокой истории |

Пилот AU+UK (2026-11-20) подтвердил: узкий Sep-only для UK может быть пустым; **широкое окно** внутри 365d даёт данные по обеим странам — см. `docs/pilot_au_uk_latest.md`.
