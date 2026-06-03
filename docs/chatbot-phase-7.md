# Chatbot Phase 7 Budget Recommendation And Adjustment

## What Phase 7 Adds

Phase 7 adds deterministic category budget guidance:

- Budget status analysis
- Budget vs actual comparison
- Budget recommendation
- Budget what-if simulation
- Confirmed budget limit updates

Budget recommendations are budgeting guidance, not investment advice.

## Formulas

- `available_for_spending = total_income - required_monthly_saving`
- `category_share = category_current_spend / total_spent`
- `recommended_category_budget = available_for_spending * adjusted_category_share`
- `budget_usage_ratio = actual_spend / budget_limit`
- `budget_remaining = budget_limit - actual_spend`
- `projected_category_spend = current_category_spend / elapsed_days * total_days`
- `projected_over_budget_amount = projected_category_spend - budget_limit`

If income is missing, recommendation confidence is low.

## Category Flexibility

Fixed categories are not aggressively reduced:

- Nha cua
- Tien thue nha
- Hoa don
- Tra no
- Giao duc
- Suc khoe
- Bao hiem

Flexible categories are prioritized for optimization:

- An uong
- Ca phe
- Dat do an
- Mua sam
- Giai tri
- Subscriptions
- Khac

## APIs

Existing:

- `GET /api/budget`
- `PATCH /api/budget/{category}`

New:

- `GET /api/budget/recommendation`
- `POST /api/budget/simulate`
- `POST /api/budget/plan`

All APIs require authenticated session for writes and chatbot-sensitive reads.

## Chatbot Tools

Read-only:

- `get_budget_status`
- `recommend_budget_plan`
- `simulate_budget_adjustment`
- `compare_budget_vs_actual`

Write tools requiring confirmation:

- `update_budget_limit`
- `upsert_budget_plan`

The chatbot cannot pass arbitrary `user_id`.

## Confirmation Behavior

User request:

`Giam ngan sach mua sam xuong 2 trieu.`

Assistant creates a pending confirmation for `update_budget_limit`. The budget is updated only after confirmation.

For a full plan, the assistant first calls `recommend_budget_plan`, asks whether to apply it, then creates a pending confirmation for `upsert_budget_plan`.

## Manual Test Questions

1. `Toi nen chia ngan sach thang nay the nao?`
2. `Toi co dang vuot ngan sach khong?`
3. `Giam ngan sach mua sam xuong 2 trieu.`
4. `Neu dat ngan sach an uong 3 trieu thi co dat muc tieu tiet kiem khong?`
5. `Ap dung ngan sach ban de xuat di.`
6. `Toi nen dau tu gi de tang ngan sach?`

Expected answer for question 6: refuse investment recommendations and redirect to budgeting/saving guidance.

## Limitations

- Recommendations use simple deterministic category share rules.
- Savings goal impact is approximate.
- No frontend redesign.
- No scheduled reminders or automatic transfers.

## Phase 8 Recommendations

1. Add richer budget history comparisons.
2. Add frontend budget recommendation cards.
3. Add stronger category normalization for multilingual category names.
4. Add explicit goal-budget integration by selected `goal_id`.
