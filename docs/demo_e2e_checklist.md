# Demo E2E checklist — TZ §17

**Цепочка:** historical SERP → unique domains → batch availability → фильтр **Available** → export.

## Автопрогон (рекомендуется)

```powershell
cd D:\Historical_SERP_Domain_Finder
# туннель на VPS :8872 должен быть up
python scripts\demo_e2e.py
```

Результат: `docs/demo_e2e_latest.md` + `docs/demo_e2e_latest.json`.

Ожидаемый spend: SERP ~$0.00012 + до 10 WhoisFreaks credits (~$0.04).

## Ручной прогон (UI)

1. Открыть `http://127.0.0.1:8872/` (SSH tunnel) → Basic login.
2. **New project:** 1–2 keywords, Australia (+ optional UK), period внутри `/api/meta/serp-window`, budget > 0 → Start.
3. Дождаться run **COMPLETED** (progress / Pause-Resume не обязательны для демо).
4. Вкладка **Domains** — есть строки `registrable_domain`.
5. **Availability estimate** → **Check availability** (или Auto after SERP).
6. Вкладка **Availability** → включить **Available only** — только `AVAILABLE_PRELIMINARY` / `AVAILABLE_CONFIRMED`; текст-предупреждение о предварительности.
7. **Export SERP files** + **Export availability** — скачать:
   - `unique_domains.txt`, `domains_summary.csv`, `positions_detailed.csv`, `coverage.csv`, `run_metadata.json`
   - `available_domains.txt`, `domain_availability.csv`, `availability_metadata.json`
8. В `available_domains.txt` нет URL, поддоменов как отдельных «мусорных» строк политики фильтра, `UNKNOWN`, дублей сверх unique set.

## Критерии PASS

| # | Критерий | PASS если |
|---|---|---|
| 1 | SERP | run COMPLETED*, snapshots ≥ 1 |
| 2 | Domains | `GET …/domains` total ≥ 1 |
| 3 | Availability job | COMPLETED / COMPLETED_WITH_GAPS / BUDGET_EXCEEDED после checks |
| 4 | Available filter | `available_only=true` не возвращает TAKEN/UNKNOWN/… |
| 5 | Export | оба набора файлов созданы; TXT available соответствует фильтру |

\* `COMPLETED_WITH_GAPS` допустим, если был хотя бы один успешный snapshot.

**Примечание:** для head-термов вроде `amazon` Available-only часто **0** — это PASS фильтра (строгость), не провал демо. Наличие строк Available зависит от SERP shortlist, не от «обязательно свободный домен в демо».
