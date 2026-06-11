# Chatbot Phase 4 Anomaly And Forecast MVP

## What Phase 4 Adds

Phase 4 adds read-only chatbot support for:

- Unusual or suspicious transactions
- Anomaly explanation
- Estimated end-of-month balance forecast
- Spending trend context

Existing Phase 2 read tools and Phase 3 confirmed write flows remain unchanged.

## New Tools

| Tool | Read/Write | Purpose |
|---|---:|---|
| `get_anomalies` | Read | Return unusual transactions for the authenticated user. |
| `get_balance_forecast` | Read | Return estimated end-of-month balance and spending trend. |
| `explain_anomaly` | Read | Explain a specific anomaly owned by the authenticated user. |

The tools are registered in `src/spectra/chat/tools.py` and executed only through `ToolExecutor`.

## Data Sources

Phase 4 uses a Spectra chatbot service wrapper in `src/spectra/chat/finance_tools.py`.

Current data source:

- `bank_transactions` for anomalies
- `bank_accounts` and recent `bank_transactions` for balance forecast

The LLM does not receive or choose `user_id`. The backend always derives `user_id` from the authenticated Spectra session.

## Anomaly Behavior

`get_anomalies` accepts:

```json
{
  "limit": 10,
  "scope": "cycle"
}
```

Rules:

- Max chatbot limit is 20.
- User answer shows at most 5 anomalies.
- Returned fields are normalized to id, date, merchant, amount, category, severity, and reason.
- Reference numbers, account numbers, tokens, and accidental raw user ids are redacted.
- Missing anomaly data returns a clear no-data message.

`explain_anomaly` is implemented for direct lookup by anomaly id. It verifies the anomaly belongs to the authenticated user before returning details.

## Forecast Behavior

`get_balance_forecast` returns:

- current balance
- estimated end-of-month balance
- average daily spending
- days remaining
- spending trend
- recommendation
- limitations

The final answer always says the result is an estimate. The chatbot must not guarantee final balances or use forecast output for investment advice.

## Supervisor Routing

The supervisor deterministically handles common Phase 4 questions before OpenAI fallback:

- `Co khoan nao bat thuong khong?` -> `get_anomalies`
- `Giao dich nao dang chu y?` -> `get_anomalies`
- `Cuoi thang toi con bao nhieu?` -> `get_balance_forecast`
- `Toi co bi am tien khong?` -> `get_balance_forecast`

Financial health score is still unsupported and remains planned for Phase 5.

## Manual Test Cases

### Anomalies

```json
{
  "message": "Co khoan nao bat thuong khong?",
  "scope": "cycle"
}
```

Expected:

- Tool call: `get_anomalies`
- Answer lists up to 5 unusual transactions
- No write tool is called

### Forecast

```json
{
  "message": "Cuoi thang toi con khoang bao nhieu?",
  "scope": "cycle"
}
```

Expected:

- Tool call: `get_balance_forecast`
- Answer includes `uoc tinh`
- Answer includes uncertainty/limitation

### Financial Health Score

```json
{
  "message": "Diem suc khoe tai chinh cua toi la bao nhieu?"
}
```

Expected:

- No tool call
- Chatbot says this will be added in a later phase

## Known Risks And Limitations

- Forecast uses Bank Simulator balances and recent debit transactions; it is not a guarantee.
- Anomaly detection uses the existing `is_anomaly` flag and `anomaly_reason` from Bank Simulator.
- Phase 4 does not add a consent database UI.
- Phase 4 does not implement Financial Health Score.
- Phase 4 does not add real bank integration.

## Phase 5 Recommendations

1. Add Financial Health Score with an explainable backend service.
2. Add persistent consent records for sensitive read tools.
3. Add database audit logs for read and write tool calls.
4. Add richer Spectra-native anomaly detection on `app_tx_history`.
5. Add frontend chat UI for anomaly cards and forecast summaries.
