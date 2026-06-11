# Chatbot Phase 5 Financial Health Score

## What Phase 5 Adds

Phase 5 adds a deterministic Financial Health Score for budgeting and cashflow quality.

New backend pieces:

- `src/spectra/financial_health.py`
- `GET /api/financial-health-score`
- Chatbot tool `get_financial_health_score`
- Deterministic supervisor routing for financial health questions

This is not investment advice, a credit score, loan eligibility scoring, or professional financial advice.

## Formula

The MVP score is normalized to 0-100 from available components:

| Component | Max |
|---|---:|
| Savings rate | 25 |
| Net cashflow | 20 |
| Spending control | 15 |
| Category balance | 15 |
| Anomaly risk | 10 |
| Forecast risk | 10 |
| Budget discipline | 5 |

If a component is unavailable, the service excludes it from the available max score when reasonable and records it in `missing_data`.

## Score Levels

| Score | Level |
|---:|---|
| 0-39 | Yeu |
| 40-59 | Can cai thien |
| 60-74 | Trung binh kha |
| 75-89 | Tot |
| 90-100 | Rat tot |

## Data Sources

- `/api/summary` for income, spending, burn rate, category breakdown, and current cycle
- `/api/budget` for budget discipline
- Phase 4 anomaly service over `bank_transactions`
- Phase 4 forecast service over `bank_accounts` and recent `bank_transactions`

## API

`GET /api/financial-health-score`

Query params:

- `scope=cycle|90d|ytd`
- `month=YYYY-MM` optional
- `refresh=false`

The current implementation calculates on demand. Snapshot persistence is deferred until a `financial_health_scores` migration is added.

## Chatbot Tool

`get_financial_health_score` is registered as read-only.

Rules:

- The backend derives `user_id` from the authenticated session.
- `user_id` in tool arguments is rejected.
- `refresh=true` from the chatbot is rejected.
- The LLM must explain the backend-calculated score and must not invent values.

## Example Questions

- `Tai chinh cua toi co on khong?`
- `Diem suc khoe tai chinh cua toi la bao nhieu?`
- `Vi sao diem cua toi thap?`
- `Toi can cai thien diem nao?`
- `Lam sao de tang diem tai chinh?`
- `Diem nay co phai diem tin dung khong?`

Expected answer for credit-score question:

`Khong. Day khong phai diem tin dung va khong dung de danh gia vay von. Day chi la diem tham khao giup ban hieu dong tien, chi tieu, rui ro bat thuong va kha nang tiet kiem.`

## Safety

The chatbot must:

- Say the score is a reference for budgeting and cashflow.
- Avoid investment recommendations.
- Avoid credit, loan, or insurance eligibility framing.
- Avoid exposing internal user ids.
- Give practical, non-shaming improvement actions.

## Limitations

- No snapshot persistence yet.
- Forecast and anomalies still depend on Bank Simulator data.
- Category balance uses simple category share rules.
- Spending control uses available burn-rate context when present.

## Phase 6 Recommendations

1. Add `financial_health_scores` migration and snapshot reuse.
2. Add month-over-month score comparison.
3. Add Spectra-native anomaly detection on `app_tx_history`.
4. Add dashboard UI card and score detail page.
