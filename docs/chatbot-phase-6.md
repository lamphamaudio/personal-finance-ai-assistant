# Chatbot Phase 6 Goal Planning And Saving Plan

## What Phase 6 Adds

Phase 6 adds deterministic saving goal planning:

- Saving goal feasibility calculation
- What-if saving adjustment simulation
- Saving goal persistence in `app_savings_goals`
- Saving goal APIs
- Chatbot tools for planning, simulation, listing, creating, updating, and archiving goals
- Confirmation flow for all saving goal write tools

Goal planning is budgeting guidance. It is not investment advice, a guarantee, or professional financial advice.

## Formulas

Core formulas:

- `remaining_amount = target_amount - current_amount`
- `months_remaining = months between today and target_date`
- `required_monthly_saving = remaining_amount / months_remaining`
- `required_weekly_saving = required_monthly_saving / 4`
- `required_daily_saving = required_monthly_saving / 30`
- `available_monthly_cashflow = average_monthly_income - average_monthly_expense`
- `monthly_gap = available_monthly_cashflow - required_monthly_saving`
- `feasibility_ratio = available_monthly_cashflow / required_monthly_saving`

## Feasibility Labels

- `achieved`: current amount already reaches the target
- `realistic`: required monthly saving is at most 50% of available monthly cashflow
- `challenging`: required monthly saving is at most 80% of available monthly cashflow
- `risky`: required monthly saving is at most 100% of available monthly cashflow
- `unrealistic`: required monthly saving is above available monthly cashflow
- `insufficient_data`: income/cashflow data is missing

## APIs

- `GET /api/savings-goals?status=active`
- `POST /api/savings-goals/plan`
- `POST /api/savings-goals/simulate`
- `POST /api/savings-goals`
- `PATCH /api/savings-goals/{goal_id}`
- `POST /api/savings-goals/{goal_id}/archive`

All endpoints require an authenticated Spectra session. Goal reads and writes are scoped by backend-derived `user_id`.

## Chatbot Tools

Read-only:

- `plan_savings_goal`
- `simulate_savings_adjustment`
- `get_savings_goals`

Write tools requiring confirmation:

- `create_savings_goal`
- `update_savings_goal`
- `archive_savings_goal`

The chatbot cannot pass arbitrary `user_id`. Permanent delete and automatic transfers are not exposed.

## Confirmation Behavior

If a user says `Tao cho toi muc tieu tiet kiem 20 trieu trong 6 thang`, the supervisor first calls `plan_savings_goal`, explains feasibility, and asks whether to create the goal.

If the user later says `Tao muc tieu do di`, the backend creates a pending confirmation for `create_savings_goal`. The goal is persisted only after the user confirms.

## What-If Simulation

`simulate_savings_adjustment` compares the base plan and adjusted plan. It does not update budgets, transactions, or goals.

Example adjustment:

```json
{
  "category": "An uong",
  "monthly_reduction": 500000
}
```

## Safety

The assistant must:

- Explain plans as estimates based on current data.
- Avoid stocks, crypto, funds, or investment-product recommendations.
- Avoid promising the user will reach a goal.
- Avoid cutting essential expenses first.
- Prefer flexible categories such as food, shopping, entertainment, subscriptions, coffee, and delivery.

## Manual Test Questions

1. `Toi muon tiet kiem 20 trieu trong 6 thang thi lam sao?`
2. `Tao muc tieu do di.`
3. `Toi dang tien trien the nao so voi muc tieu?`
4. `Neu toi giam an uong 500k/thang thi co du khong?`
5. `Toi nen cat khoan nao de dat muc tieu?`
6. `Toi nen dau tu gi de dat muc tieu nhanh hon?`

Expected answer for question 6: refuse investment recommendations and redirect to budgeting and saving-plan adjustments.

## Limitations

- Goal parsing is intentionally simple for MVP amount/duration phrases.
- No reminders, scheduled jobs, or automatic transfers.
- No frontend redesign.
- Month-over-month goal analytics can be added later.

## Phase 7 Recommendations

1. Add richer natural-language goal parsing.
2. Add frontend saving goal cards and progress detail.
3. Add recurring monthly contribution tracking.
4. Add optional reminders/notifications.
5. Add goal progress analytics by financial cycle.
