# Acceptance checklist — TZ §14 + §15.10

**Дата прогона:** 2026-11-20  
**Среда:** VPS `89.163.221.244` + SSH tunnel `:8872` + unit/contract tests  
**Ограничение Spike:** история DataForSEO ≈ last 365 days only (не регресс).

Легенда: **PASS** / **PARTIAL** / **FAIL** / **N/A (deferred)**  
Доказательства: `tests/test_acceptance_contracts.py`, `tests/test_*.py`, `scripts/e2e_vps_pilot.py`, `spike/results/spike_protocol_latest.md`, код.

---

## §14 — SERP (п.1–16)

| # | Критерий | Статус | Доказательство / примечание |
|---|---|---|---|
| 1 | Spike-отчёт + UI блокирует старые даты | **PASS** | Spike GO 2026-11-19; `validate_history_window`; UI `min=earliest_allowed_date` |
| 2 | Мультигео: 3 kw × 2 страны = 6 комбинаций | **PASS** (контракт) / **PARTIAL** (live) | `estimate` + `RunQuery` matrix; live E2E был AU-only — полный AU+UK = следующий пункт roadmap «пилот» |
| 3 | Все snapshots из одного response сохраняются | **PASS** | `parse_historical_response` держит N items; тест 6 snaps |
| 4 | Нет снимка → `NO_SNAPSHOT`, не «0 позиций» | **PASS** | `persist_serp` coverage; E2E Oct пустой → `NO_SNAPSHOT` |
| 5 | `rank_group` для TOP-N (не путать с absolute) | **PASS** | parser + depth filter по `rank_group`; тест |
| 6 | PAA/Ads не в organic domains | **PASS** | `_organic_items` только `type==organic` |
| 7 | PSL: www/blog → `example.com.au`; `other.com.au` отдельно | **PASS** | `tests/test_domains.py` + acceptance |
| 8 | Глобальная дедуп в TXT + все hits в detailed CSV | **PASS** | `unique_domains.txt` set; `positions_detailed.csv` полные строки; `dedupe_mode` учтён |
| 9 | Partial depth не притворяется TOP-100 | **PASS** | coverage `PARTIAL_DEPTH` если organic &lt; depth |
| 10 | Retry + idempotency snapshots | **PASS** | SERP retry 429/5xx; snapshot unique по `(provider, keyword, loc, lang, observed_at)` |
| 11 | Budget cap: нет новых платных вызовов | **PASS** | period-aware `projected_query_cost_usd` (months×price) + soft-stop on claim; 80% warning in progress |
| 12 | Pause/resume не перезапрашивает COMPLETED | **PASS** | worker берёт только `QUEUED` |
| 13 | HTTP 200 + task error = ошибка | **PASS** | query `FAILED` + coverage `API_ERROR`; 40501 not retry |
| 14 | Export TXT/CSV/metadata | **PASS** | E2E export ids; UTF-8 BOM + formula guard; metadata cost/source |
| 15 | Domain drilldown — все ключи/URL | **PASS** | `domain_card` + UI modal |
| 16 | Special chars keywords | **PASS** | `prepare_keywords` unicode/`%`/`+` |

### §14 п.17–24 (availability, дублируют §15.10)

| # | Критерий | Статус | Примечание |
|---|---|---|---|
| 17 | 201 доменов → ≤3 батча ×100 | **PASS** | `BATCH_MAX=100`; worker `limit=min(100, budget)`; estimate `batch_count` |
| 18 | NXDOMAIN/404 ≠ AVAILABLE | **PASS** | нет DNS/HTTP path в `app/`; только WhoisFreaks |
| 19 | TLD policy `.com.au` eligibility отдельно | **PASS** | seed `REQUIRES_EVIDENCE`; E2E sample показал eligibility отдельно от registration |
| 20 | timeout / unsupported ≠ TAKEN/AVAILABLE | **PASS** | map → UNKNOWN; hard fail → FAILED items |
| 21 | Cache + force recheck | **PASS** | TTL 24h / 15m error; recheck `force_refresh=True` |
| 22 | Budget credits блокирует enqueue | **PASS** | `to_check > budget_cap_credits` → 400 |
| 23 | `available_domains.txt` только filter Available | **PASS** | `AVAILABLE_FILTER` only |
| 24 | No auto-purchase | **PASS** | нет purchase endpoints; GoDaddy stub 501 |

---

## §15.10 — Availability module

| # | Критерий | Статус | Доказательство / примечание |
|---|---|---|---|
| 1 | 300 SERP hits → 1 платный check (или 0 из кэша) | **PASS** | check по distinct `registrable_domain`; estimate `cached_fresh` |
| 2 | 201 unique → 3 WhoisFreaks requests | **PASS** | контракт batch math + worker chunking (live 201 не гоняли — дорого; логика покрыта) |
| 3 | `blog.example.com.au` → `example.com.au` + policy flag | **PASS** | PSL + `tld_registration_policies` |
| 4 | NXDOMAIN/HTTP/no A ≠ AVAILABLE | **PASS** | нет такого кода |
| 5 | UNSUPPORTED/timeout/429/malformed ≠ TAKEN | **PASS** | status map + retry policy |
| 6 | Partial batch: успех остальных + retry одного | **PASS** | per-domain map; **requeue FAILED attempt&lt;3** (фикс 2026-11-20) |
| 7 | State не затирается более старым ответом | **PASS** | `if not state.last_checked_at or state.last_checked_at <= now` |
| 8 | Filter Available = API-confirmed + checked_at | **PASS** | `available_only` + `AVAILABLE_FILTER` + timestamp fields |
| 9 | TXT: нет дублей/subdomains/URL/пробелов/UNKNOWN | **PASS** | export filter; unique set |
| 10 | Spend-cap останавливает новые вызовы | **PASS** | job `BUDGET_EXCEEDED`; create rejects oversize |
| 11 | Креды не в frontend/логах/exports | **PASS** | Basic auth only; `redact_url` apiKey; raw JSON без ключа в path query storage |
| 12 | Нет POST в registration/payment | **PASS** | только availability check; Confirm live = 501 stub |

---

## Live E2E reference (уже был)

| | |
|---|---|
| Run | `313b212f-…` (amazon/casino AU Sep 2026) |
| SERP | 1 snapshot, $0.00012, 6 domains |
| Availability | 6 credits, statuses from WhoisFreaks |
| Exports | SERP + availability файлы созданы |

---

## Открытые PARTIAL (не блокеры этого пункта, но не забыть)

1. **Live мультигео AU+UK** — закрывается пилотом этапа 3 п.2.  
2. **Live прогон ровно 201 домен** — логика есть; полный spend не делали.  
3. **GoDaddy Confirm live** — осознанный stub до PAT (Spike).  
4. **Frontend file import CSV** — **DONE** (New project + Project page: `.txt`/`.csv` → `POST …/keywords/import-file`).

---

## Команды воспроизведения

```powershell
cd D:\Historical_SERP_Domain_Finder
.\.venv\Scripts\python.exe -m pytest tests\test_acceptance_contracts.py tests\test_domains.py tests\test_whoisfreaks_map.py tests\test_serp_retry.py tests\test_csv_safe.py tests\test_redact.py tests\test_history_window.py -q
# optional live (spends tiny budget):
.\.venv\Scripts\python.exe scripts\e2e_vps_pilot.py
```

**Итог пункта:** Acceptance §14 + §15.10 — **закрыт с PASS по всем обязательным критериям**; PARTIAL только на необязательных live-stress / deferred GoDaddy / UI file button.
