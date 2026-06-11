# Chatbot Phase 9 Insight Tools

## What Phase 9 Adds

Phase 9 adds deterministic read-only insight tools for common personal-finance questions that need current data and should not be answered from chat memory or LLM estimation alone.

Implemented:

- Recurring payments and subscription insight.
- Current-vs-previous period spending comparison.
- Budget overrun explanation with top transaction drivers.
- Estimated cashflow calendar.
- Planned purchase impact simulation.
- Debt-like payment summary.
- Emergency fund coverage estimate.

No write tools, migrations, scheduled reminders, debt ledger, or new public HTTP APIs are added in this phase.

## Chatbot Tools

All Phase 9 tools are read-only, session-scoped, non-dangerous, and executed only through `ToolExecutor`.

| Tool | Purpose | Scope |
|---|---|---|
| `get_recurring_transactions` | Detect estimated recurring payments, subscriptions, recurring income, and price changes. | `analytics.read` |
| `compare_period_spending` | Compare spending, income, category deltas, merchant deltas, and transaction counts between periods. | `analytics.read` |
| `explain_budget_overrun` | Explain which categories and transactions are driving over-budget or at-risk status. | `budget.read` |
| `get_cashflow_calendar` | Estimate daily balance checkpoints and upcoming recurring events. | `forecast.read` |
| `simulate_purchase_impact` | Simulate how a one-off purchase affects budget, forecast balance, and active saving goals. | `forecast.read` |
| `get_debt_summary` | Infer debt-like payments from transaction history. | `analytics.read` |
| `get_emergency_fund_status` | Estimate emergency fund months covered from current balance and essential spending. | `forecast.read` |

The LLM cannot pass arbitrary `user_id` to these tools. If `user_id` appears in tool arguments, `ToolExecutor` rejects the call.

## Data Sources

Phase 9 uses existing data only:

- `app_tx_history` for transaction history, merchants, categories, amounts, and descriptions.
- Existing budget payload from `api_budget`.
- Existing summary payload from `api_summary`.
- Existing forecast payload from `get_balance_forecast`.
- Existing saving goals from `get_savings_goals`.

There is no new database table in Phase 9.

## Supervisor Routing

The supervisor handles common Vietnamese prompts deterministically before the OpenAI fallback:

- `khoan dinh ky`, `subscription`, `co dinh`, `lap lai`, `hang thang` -> `get_recurring_transactions`
- `thang nay so voi thang truoc`, `tang giam o dau`, `khac gi thang truoc` -> `compare_period_spending`
- `tai sao`, `vi sao`, `ly do` with `ngan sach` -> `explain_budget_overrun`
- `lich dong tien`, `ngay nao thieu tien`, `tu gio toi cuoi thang` -> `get_cashflow_calendar`
- `mua ... co on khong`, `neu chi ... thi sao` -> `simulate_purchase_impact`
- `tra gop`, `tra no`, `khoan no`, `con no` -> `get_debt_summary`
- `quy khan cap`, `song duoc may thang`, `mat thu nhap` -> `get_emergency_fund_status`

The tools are also registered in `openai_tool_definitions()`, so the LLM can select them when a question does not match deterministic routing.

## Safety Rules

- The assistant must not calculate recurring totals, period deltas, cashflow dates, purchase impact, debt-like totals, or emergency-fund coverage by itself.
- Cashflow calendar and purchase simulation are estimates, not guaranteed future balances.
- Debt v1 is inference only. If `outstanding_balance_available=false`, the assistant must say it only sees debt-like payments and cannot conclude the remaining debt balance.
- Phase 9 tools do not mutate transactions, budgets, goals, memories, or reminders.
- Admin/destructive tools remain unavailable.

## Example Questions

1. `Toi co khoan dinh ky nao hang thang?`
2. `Thang nay toi chi nhieu hon thang truoc o dau?`
3. `Tai sao toi vuot ngan sach an uong?`
4. `Ngay nao toi de thieu tien tu gio toi cuoi thang?`
5. `Toi mua dien thoai 15 trieu thang nay co on khong?`
6. `Toi con khoan no tra gop nao khong?`
7. `Quy khan cap cua toi du chua?`
8. `Neu mat thu nhap thi toi song duoc may thang?`

## Implementation Files

- `src/spectra/chat/insight_tools.py`: deterministic helper implementations.
- `src/spectra/chat/tools.py`: tool registry and JSON schemas.
- `src/spectra/chat/executor.py`: executor dispatch and backend data wiring.
- `src/spectra/chat/supervisor.py`: deterministic routing and fallback answer formatting.
- `src/spectra/chat/prompts.py`: Phase 9 tool-use and safety instructions.

## Tests

Coverage added:

- Registry contains all 7 tools and marks them read-only.
- Executor rejects `user_id` arguments for Phase 9 tools.
- Executor clamps bounded arguments such as `limit` and `days`.
- Helper tests cover recurring detection, period comparison, budget overrun drivers, purchase simulation labels, debt limitations, and emergency fund calculation.
- Supervisor tests cover representative Vietnamese prompts for all 7 routes.

Validation command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\chatbot
```

Current result:

```text
112 passed
```

## Limitations

- Recurring detection is heuristic and based on merchant, amount stability, cadence, category, and known recurring patterns.
- Debt summary does not know outstanding balance, interest rate, due date, minimum payment, or payoff schedule.
- Cashflow calendar estimates future events from recurring history and recent spending; it is not a bill calendar.
- Emergency fund status uses inferred essential categories and current balance; it is not a full financial plan.
- No frontend-specific UI is added for Phase 9 insight cards.

## Phase 10 Recommendations

1. Add explicit bill/reminder data model and reminder UI.
2. Add user-entered debt ledger with balance, APR, minimum payment, and due date.
3. Add richer recurring transaction review UI with confirm/ignore actions.
4. Add dedicated insight cards in chat responses for comparison, cashflow, and emergency fund results.
5. Add evaluation dataset rows for Phase 9 routes.
