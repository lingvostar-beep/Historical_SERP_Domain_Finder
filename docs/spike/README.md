# Spike protocol — поставка (TZ §17)

Каноническая **доставляемая** копия Spike (без секретов).  
Рабочие сырые дампы по-прежнему локально в `spike/results/` (gitignore).

| Файл | Назначение |
|---|---|
| [`spike_protocol_latest.md`](spike_protocol_latest.md) | Протокол + Go/No-go (текст) |
| [`spike_protocol_latest.json`](spike_protocol_latest.json) | Машиночитаемый протокол (запросы/cost/статусы) |
| [`spike_protocol_GO_2026-11-19.md`](spike_protocol_GO_2026-11-19.md) | Подписанный GO от 2026-11-19 |
| [`../history_availability_table.md`](../history_availability_table.md) | Таблица доступной истории (выжимка) |

**Решение:** GO MVP с лимитом истории ≈ **последние 365 дней**. Primary SERP = `dataforseo_google_current`. WhoisFreaks = primary availability. GoDaddy Confirm deferred.

Контрактные тесты на фикстурах: `tests/fixtures/spike/` + `tests/test_spike_contracts.py`.  
Примеры raw/normalized: `docs/examples_raw_normalized.md`.
