# Spike Go / No-go — checklist (Этап 0)

**Статус: GO MVP с ограничением — подписано 2026-11-19**

Полный протокол: `spike/results/spike_protocol_latest.md`

## DataForSEO

| Вопрос | Ответ |
|---|---|
| Legacy отдал снимки за 2022-05 (AU)? | **Нет** — `40501 Invalid Field: date_from` |
| Legacy отдал снимки за 2023-05 (AU)? | **Нет** — то же |
| Legacy отдал снимки за 2024-05 (AU)? | **Нет** — то же |
| Legacy отдал снимки за 2023-05 (UK)? | **Нет** — то же |
| Current / Legacy без старых дат (casino AU)? | **Да** — 6 снимков ~ноя 2025 – авг 2026 |
| Current на 2022-05 | **40501** (ожидаемо / вне окна) |
| Хватает organic под TOP-10/20/50/100? | Часто да (до 100); свежие снимки 27–50 → PARTIAL_DEPTH |
| Реальный cost | ~**$0.00012** / snapshot |
| Плата «за запрос» сверх snapshot? | По пробам cost ≈ N×0.00012; пустые/ошибки ≈ 0 |

## WhoisFreaks

| Вопрос | Ответ |
|---|---|
| taken (`google.com` / `example.com`) | `UNAVAILABLE` |
| random `.com` | `AVAILABLE` |
| `example.com.au` | `UNAVAILABLE` |
| bad TLD | `UNKNOWN` (не путать с TAKEN/AVAILABLE) |
| Enum для MVP | `AVAILABLE` / `UNAVAILABLE` / `UNKNOWN` |

## GoDaddy

| Вопрос | Ответ |
|---|---|
| Доступ | **Не настроен** — Confirm live отложен |
| MVP без `AVAILABLE_CONFIRMED`? | **Да** |

## Решение

- [x] **GO с ограничением** — MVP только на истории ≈ **последние 365 дней**
- [x] Primary SERP: `dataforseo_google_current` (Legacy не даёт более глубокий архив на этом аккаунте)
- [x] UI **не** предлагает 2021–2024 на DataForSEO
- [x] WhoisFreaks — primary availability
- [x] 2021–2024 / 2015–2020 — только Phase 2 (другой провайдер), вне MVP

**Подпись / дата:** оператор + агент, 2026-11-19
