# Chatbot API Inventory

Phase 1 audit for Personal Finance AI Assistant v3. This document inventories the current backend API surface and maps existing capabilities to possible tools for an LLM chatbot supervisor.

No chatbot logic, `/api/chat` endpoint, or business logic changes are included in this phase.

## 1. Repository Overview

### FastAPI Applications

| Application | Entry Point | Purpose | Chatbot v3 Relevance |
|---|---|---|---|
| Spectra main service | `src/spectra/web/server.py:59` | Main FastAPI dashboard/API service for auth, transaction history, summary analytics, categories, rules, learning, imports, budget, trends, and subscriptions. | Primary service to wrap as chatbot tools. |
| Bank Simulator | `bank_simulator/main.py:65` | FastAPI demo bank service with bank auth/session/SSO, bank transactions, summary, anomalies, prediction, users, and stats. | Useful for bank-linked tools, anomaly explanation, and balance forecast. |

No `APIRouter` declarations were found. Routes are registered directly on `app`.

### Important Files

| File Path | Purpose | Important Functions / Classes | Relevant to Chatbot v3? |
|---|---|---|---|
| `src/spectra/web/server.py` | Main FastAPI API and HTML server. | `app`, `_read_session_user_id`, `_set_session_cookie`, `_verify_bank_sso_token`, `_fetch_demo_user`, `_fetch_bank_transactions`, `_persist_learning`, `_simulate_rule_impact`, `api_summary`, `api_transactions`, `api_update_transaction`, `api_categories_options`, `api_get_category_rules`, `api_learning_summary`, `api_budget`, `api_trends`, `api_subscriptions`. | Yes. Primary source for tool wrappers. |
| `src/spectra/db.py` | Database abstraction for Spectra app tables. | `BookmarkDB`, `save_history`, `get_budget_limits`, `save_budget_limit`, `get_category_rules`, `add_category_rule`, `update_category_rule`, `delete_category_rule`, `save_learning_feedback`, `get_recent_learning_feedback`, `reapply_learning_to_history`, `reset_all_data`. | Yes. Tool executor should call APIs/services, not direct DB, but this defines persistence behavior. |
| `src/spectra/config.py` | Runtime settings. | `Settings`, `load_settings`. | Yes. Needed for chatbot model/provider and service config. |
| `src/spectra/ai.py` | LLM/local transaction categorization support. | `CategorySuggestion`, `CategorisedTransaction`, `categorise`. | Yes for categorization context, not yet chatbot supervisor. |
| `src/spectra/local_categorizer.py` | Deterministic/local categorization. | `categorise_local`. | Yes for category correction and future tool explanations. |
| `src/spectra/ml_classifier.py` | ML classifier helpers for categorization. | `train_classifier`. | Maybe. Useful for category suggestions, not required for MVP chat. |
| `src/spectra/categories.py` | Category normalization and seed category helpers. | `normalize_category`, `normalize_recurring`, `build_seed_data`, constants such as `UNCATEGORIZED`. | Yes. Category tools should reuse this normalization. |
| `src/spectra/rules.py` | Category rule matching/normalization. | `VALID_RULE_TYPES`, `normalize_rule_type`, rule matching helpers. | Yes. Used by category rule tools. |
| `src/spectra/budget.py` | Google Sheets budget helpers and budget status computation. | `read_budgets`, `sync_budget_sheet`, `compute_budget_status`. | Maybe. API already computes budget status in `server.py`. |
| `src/spectra/trends.py` | Google Sheets trend refresh helpers. | `refresh_trends`. | Maybe. API already computes trends in `server.py`. |
| `src/spectra/recurring.py` | Recurring payment/subscription detection. | `apply_recurring_tags`, `detect_recurring_kind`. | Yes for subscriptions and recurring spend explanation. |
| `bank_simulator/main.py` | Bank Simulator FastAPI API. | `app`, `Transaction`, `SpendingSummary`, `AnomalyTransaction`, `PredictionResponse`, `UserInfo`, `OverallStats`, `read_session_user_id`, `require_bank_user`, `get_transactions`, `get_spending_summary`, `get_anomalies`, `get_balance_prediction`. | Yes for bank data tools. |
| `bank_simulator/data_seeder.py` | Seed bank users, transactions, transaction patterns, and anomaly flags. | `generate_transactions_for_user`, `calculate_transaction_patterns`, `generate_anomaly_reason`. | Maybe. Explains anomaly source; not a runtime chatbot API. |
| `bank_simulator/seed_missing_transactions.py` | Seeds missing bank activity. | `seed_missing_transactions`. | No for MVP chatbot. |
| `supabase/migrations/0001_initial_schema.sql` | Spectra app tables. | `app_tx_history`, `app_user_overrides`, `app_category_rules`, `app_learning_feedback`. | Yes. Missing chat/audit/consent tables should be added near this schema family. |
| `supabase/migrations/0002_bank_simulator_schema.sql` | Bank simulator schema. | `bank_transactions`, `transaction_patterns`, views/functions/triggers. | Yes for bank simulator tool semantics. |
| `frontend/src/api/services.js` | Frontend API client wrappers. | `getSummary`, `getTransactions`, `updateTransaction`, `bulkUpdateCategory`, settings/rules/budget/trends/subscription calls. | Yes. Confirms which APIs are consumed by UI. |

## 2. API Inventory

### Bank Simulator Routes

| Service | Method | Path | Params / Body | Response Shape | Source File | Source Line | Chatbot Tool Candidate? | Required Permission Scope | Notes |
|---|---:|---|---|---|---|---:|---|---|---|
| Bank Simulator | GET | `/` | Cookie session. | Redirect to `/dashboard` or `/login`. | `bank_simulator/main.py` | 540 | No | `public.read` | HTML navigation only. |
| Bank Simulator | GET | `/health` | None. | `{service,status,version,endpoints[]}` | `bank_simulator/main.py` | 548 | No | `public.read` | Health/debug endpoint. |
| Bank Simulator | GET | `/login` | Query `return_to?`. | HTML login page. | `bank_simulator/main.py` | 568 | No | `public.read` | UI page. |
| Bank Simulator | POST | `/login` | JSON `{username,password,return_to?}`. | `{ok,user,redirect_url}` and session cookie. | `bank_simulator/main.py` | 639 | No | `public.read` | Auth endpoint, not an LLM tool. |
| Bank Simulator | GET | `/sso/start` | None. | Redirect to Spectra SSO. | `bank_simulator/main.py` | 654 | No | `public.read` | SSO navigation. |
| Bank Simulator | GET | `/sso/entry` | Query `return_to?`, cookie session. | HTML consent page or redirect to login. | `bank_simulator/main.py` | 659 | No | `session.read` | Existing consent is bank SSO consent, not chatbot tool consent. |
| Bank Simulator | POST | `/sso/confirm` | JSON `{consent,return_to?}`, cookie session. | `{ok,redirect_url}` | `bank_simulator/main.py` | 734 | No | `session.read` | Confirms Bank to Spectra SSO. |
| Bank Simulator | GET | `/sso/callback` | Query `token`. | Redirect to `/dashboard` and session cookie. | `bank_simulator/main.py` | 748 | No | Valid SSO token | Auth callback only. |
| Bank Simulator | POST | `/logout` | None. | `{ok}` | `bank_simulator/main.py` | 768 | No | `session.read` | Clears bank session cookie. |
| Bank Simulator | GET | `/me` | Cookie session. | `{user}` | `bank_simulator/main.py` | 775 | Yes | `account.read_basic` | Useful identity/profile context. |
| Bank Simulator | GET | `/dashboard` | Cookie session. | HTML dashboard page. | `bank_simulator/main.py` | 788 | No | `session.read` | UI page. |
| Bank Simulator | GET | `/transactions` | Query `user_id?`, `limit`, `offset`, `category?`, `start_date?`, `end_date?`. | `Transaction[]`: `{id,user_id,account_id,transaction_type,amount,merchant,merchant_category,category,description,balance_after,is_anomaly,anomaly_reason,location,payment_method,reference_number,created_at}` | `bank_simulator/main.py` | 989 | Yes | `transactions.read_detail` | Uses `require_bank_user(request, user_id)`. Raw details and balances are sensitive. |
| Bank Simulator | GET | `/summary` | Query `user_id?`, `days`. | `SpendingSummary`: `{user_id,total_spending,total_income,net_cashflow,categories[],period_days}` | `bank_simulator/main.py` | 1058 | Yes | `analytics.read` | Uses `require_bank_user`. Good aggregate tool. |
| Bank Simulator | GET | `/anomalies` | Query `user_id?`, `limit`. | `AnomalyTransaction[]`: `{id,amount,merchant,category,anomaly_reason,created_at,severity}` | `bank_simulator/main.py` | 1142 | Yes | `anomaly.read` | Uses `require_bank_user`. Good for anomaly explanations. |
| Bank Simulator | GET | `/prediction` | Query `user_id?`. | `PredictionResponse`: `{user_id,current_balance,predicted_end_of_month_balance,avg_daily_spending,days_remaining,spending_trend,recommendation}` | `bank_simulator/main.py` | 1202 | Yes | `forecast.read` | Uses `require_bank_user`. Contains balance data. |
| Bank Simulator | GET | `/users` | Query `limit`, `persona_type?`. | `UserInfo[]`: `{user_id,persona_type,account_number,bank_name,current_balance,transaction_count,anomaly_count}` | `bank_simulator/main.py` | 1307 | No | `admin.read` | Public currently. Should not be exposed to normal chatbot users. |
| Bank Simulator | GET | `/stats` | None. | `OverallStats`: `{total_users,total_transactions,total_anomalies,anomaly_rate,total_volume,personas}` | `bank_simulator/main.py` | 1373 | No | `admin.read` | Public currently. Admin/debug only. |

### Spectra Routes

| Service | Method | Path | Params / Body | Response Shape | Source File | Source Line | Chatbot Tool Candidate? | Required Permission Scope | Notes |
|---|---:|---|---|---|---|---:|---|---|---|
| Spectra | GET | `/login` | None. | HTML/React app. | `src/spectra/web/server.py` | 698 | No | `public.read` | UI page. |
| Spectra | GET | `/api/auth/me` | Cookie session. | `{user}` or `401 {error}` | `src/spectra/web/server.py` | 703 | Yes | `account.read_basic` | Good `get_current_user` tool. |
| Spectra | GET | `/api/auth/demo-users` | None. | `{users[]}` | `src/spectra/web/server.py` | 716 | No | `public.read` | Public demo user listing. Do not expose to normal chatbot. |
| Spectra | POST | `/api/auth/login` | JSON `{user_id}`. | `{ok,user}` and session cookie. | `src/spectra/web/server.py` | 721 | No | `public.read` | Demo login endpoint. |
| Spectra | POST | `/api/auth/logout` | None. | `{ok}` | `src/spectra/web/server.py` | 735 | No | `session.read` | Clears session cookie. |
| Spectra | GET | `/sso/bank` | None. | Redirect to Bank Simulator SSO entry. | `src/spectra/web/server.py` | 743 | No | `public.read` | SSO navigation. |
| Spectra | GET | `/sso/bank/callback` | Query `token`. | Redirect and session cookie or `401 {error}`. | `src/spectra/web/server.py` | 754 | No | Valid SSO token | Auth callback only. |
| Spectra | GET | `/` | Cookie session. | HTML/React dashboard. | `src/spectra/web/server.py` | 770 | No | `session.read` | UI page. |
| Spectra | GET | `/transactions` | Cookie session. | HTML/React transactions page. | `src/spectra/web/server.py` | 777 | No | `session.read` | UI page. Duplicate declaration also exists at line 800. |
| Spectra | GET | `/upload` | Cookie session. | HTML/React upload page. | `src/spectra/web/server.py` | 784 | No | `session.read` | UI page. Duplicate declaration also exists at line 807. |
| Spectra | GET | `/settings` | None in active handler. | HTML/React settings page. | `src/spectra/web/server.py` | 791 | No | `session.read` | The first handler returns before auth redirect logic. Duplicate declaration also exists at line 814. |
| Spectra | GET | `/transactions` | Cookie session. | HTML/React transactions page. | `src/spectra/web/server.py` | 800 | No | `session.read` | Duplicate route declaration. |
| Spectra | GET | `/upload` | Cookie session. | HTML/React upload page. | `src/spectra/web/server.py` | 807 | No | `session.read` | Duplicate route declaration. |
| Spectra | GET | `/settings` | None in handler. | HTML/React settings page. | `src/spectra/web/server.py` | 814 | No | `session.read` | Duplicate route declaration; no explicit session check. |
| Spectra | GET | `/subscriptions` | Cookie session. | HTML/React subscriptions page. | `src/spectra/web/server.py` | 819 | No | `session.read` | UI page. |
| Spectra | GET | `/api/summary` | Query `scope=cycle|90d|ytd`. | `{total_spent,total_income,subscriptions,uncategorized,uncategorized_total,by_category,monthly,monthly_ranges,top_merchants,current_cycle,scope,scope_label,selected_period,has_data,burn_rate,insights,...preferences}` | `src/spectra/web/server.py` | 829 | Yes | `analytics.read` | Uses `_read_session_user_id(request) or ""`; should return 401 before chatbot exposure. |
| Spectra | GET | `/api/transactions` | Query `page`, `per_page`, `category`, `uncategorized_only`, `search`, `date_from`, `date_to`. | `{transactions:[{id,date,merchant,category,amount}],total,uncategorized_total,page,per_page,pages}` | `src/spectra/web/server.py` | 987 | Yes | `transactions.read_detail` | Uses `_read_session_user_id(request) or ""`; raw details are sensitive. |
| Spectra | PATCH | `/api/transactions/{tx_id}` | Path `tx_id`; JSON `{category?,merchant?,apply_to_future?}`. | `{ok,id}` or `{error}` | `src/spectra/web/server.py` | 1076 | Yes | `category.update` | Write tool. Needs explicit confirmation and session/user ownership enforcement. |
| Spectra | POST | `/api/transactions/bulk-category` | JSON `{ids[],category,apply_to_future?}`. | `{ok,updated,category}` or `{error}` | `src/spectra/web/server.py` | 1127 | Yes | `category.update` | Write tool. Needs confirmation and ownership enforcement. |
| Spectra | GET | `/api/categories` | None. | `{categories[]}` | `src/spectra/web/server.py` | 1173 | Yes | `categories.read` | No explicit session filter; returns global known categories. |
| Spectra | GET | `/api/categories/options` | Cookie session. | `{categories[]}` | `src/spectra/web/server.py` | 1184 | Yes | `categories.read` | Uses `_read_session_user_id(request) or ""`; includes seed categories. |
| Spectra | GET | `/api/settings` | None. | `{provider,currency,requires_base_currency_setup,tx_count,merchant_count,feedback_count,active_rule_count,category_count,sheets_connected,...preferences,current_cycle}` | `src/spectra/web/server.py` | 1200 | Maybe | `session.read` | No explicit session check. Includes global counts/settings. |
| Spectra | PATCH | `/api/settings/preferences` | JSON `{theme_preference?,base_currency?,pay_day?,cycle_start_day?,cycle_mode?}`. | `{ok,...preferences,currency,requires_base_currency_setup,current_cycle}` | `src/spectra/web/server.py` | 1233 | Maybe | `budget.write` / `session.write` | Settings write. Needs confirmation. |
| Spectra | GET | `/api/settings/rules` | None. | `{rules,valid_rule_types,summary}` | `src/spectra/web/server.py` | 1306 | Yes | `rules.read` | No explicit session check. Rules appear global. |
| Spectra | POST | `/api/settings/rules` | JSON `{rule_type?,pattern,category}`. | `{ok,rule}` or `{error}` | `src/spectra/web/server.py` | 1322 | Yes | `rules.write` | Write tool. Needs confirmation. |
| Spectra | PATCH | `/api/settings/rules/{rule_id}` | Path `rule_id`; JSON `{move?,is_active?}`. | `{ok,rule}` or `{error}` | `src/spectra/web/server.py` | 1354 | Yes | `rules.write` | Write tool. Needs confirmation. |
| Spectra | POST | `/api/settings/rules/test` | JSON `{rule_type?,pattern,sample_text?}`. | `{ok,matched_sample,impact_count,examples...}` | `src/spectra/web/server.py` | 1381 | Yes | `rules.read` | Safe read/test if output is bounded. |
| Spectra | DELETE | `/api/settings/rules/{rule_id}` | Path `rule_id`. | `{ok,id}` or `{error}` | `src/spectra/web/server.py` | 1415 | Yes | `rules.write` | Destructive rule write. Needs confirmation. |
| Spectra | GET | `/api/settings/learning` | None. | `{events,summary:{feedback_count,override_count,uncategorized_count,learned_future_count}}` | `src/spectra/web/server.py` | 1425 | Yes | `memory.read` | No explicit session check. Recent learning events can expose transaction metadata. |
| Spectra | POST | `/api/settings/learning/reapply` | None. | `{ok,...result}` | `src/spectra/web/server.py` | 1451 | Maybe | `memory.write` | Reprocesses history. Needs confirmation and should wait. |
| Spectra | POST | `/api/settings/reset-db` | JSON `{confirm:"RESET"}`. | `{ok,message,deleted}` or `{ok:false,error}` | `src/spectra/web/server.py` | 1459 | No | `destructive.write` | Must never be registered as chatbot tool. No explicit session check. |
| Spectra | POST | `/api/import-bank` | Cookie session. | SSE stream; progress events and final preview `{transactions[],message}`. | `src/spectra/web/server.py` | 1699 | Maybe | `transactions.read_detail` / `memory.write` | Import workflow, not a simple MVP chat tool. Requires session. |
| Spectra | POST | `/api/upload` | Multipart file `file` with `.csv`, `.pdf`, or `.ofx`. | SSE stream; progress events and final preview transactions. | `src/spectra/web/server.py` | 1739 | No | `transactions.write` | File upload workflow. Not suitable as LLM tool. |
| Spectra | POST | `/api/confirm` | JSON `{transactions[]}`. | `{ok,message}` | `src/spectra/web/server.py` | 1972 | Maybe | `transactions.write` / `memory.write` | Persists imported transactions and learning. Needs confirmation. |
| Spectra | GET | `/budget` | Cookie session. | HTML/React budget page. | `src/spectra/web/server.py` | 2065 | No | `session.read` | UI page. |
| Spectra | GET | `/trends` | Cookie session. | HTML/React trends page. | `src/spectra/web/server.py` | 2072 | No | `session.read` | UI page. |
| Spectra | GET | `/api/budget` | Cookie session. | `{current_cycle,items:[{category,spent,limit,pct,status}],summary:{on_track,over,no_limit}}` | `src/spectra/web/server.py` | 2082 | Yes | `budget.read` | Uses `_read_session_user_id(request) or ""`; should return 401 before exposure. |
| Spectra | PATCH | `/api/budget/{category}` | Path `category`; JSON `{limit}`. | `{ok,category,limit}` or `{error}` | `src/spectra/web/server.py` | 2154 | Yes | `budget.write` | Write tool. Needs confirmation. |
| Spectra | GET | `/api/trends` | Cookie session. | `{years,by_year,period_series,...preferences}` | `src/spectra/web/server.py` | 2171 | Yes | `trends.read` | Uses `_read_session_user_id(request) or ""`; should return 401 before exposure. |
| Spectra | GET | `/api/subscriptions` | Cookie session. | `{items:[{merchant,category,last_amount,average_amount,cadence_days,last_charge_date,next_estimated_date,monthly_estimate,annual_projection,in_current_cycle,payments_count,price_change_direction,change_amount,change_pct}],summary,current_cycle}` | `src/spectra/web/server.py` | 2251 | Yes | `subscriptions.read` | Uses `_read_session_user_id(request) or ""`; sensitive merchant data. |

## 3. Chatbot Tool Mapping

| Chatbot Tool Name | User Intent | Existing Endpoint | Service | Read/Write | Required Scope | Needs Confirmation? | Safe For MVP? | Notes |
|---|---|---|---|---|---|---|---|---|
| `get_current_user` | ACCOUNT_SUMMARY, PRIVACY_OR_PERMISSION | `GET /api/auth/me` | Spectra | Read | `account.read_basic` | No | Yes | First safe tool. |
| `get_account_summary` | ACCOUNT_SUMMARY, SAVING_SUGGESTION | `GET /api/summary` | Spectra | Read | `analytics.read` | No | Yes, after auth hardening | Aggregate output is appropriate for chat. |
| `get_spending_breakdown` | SPENDING_BREAKDOWN, CATEGORY_ANALYSIS | `GET /api/summary` | Spectra | Read | `analytics.read` | No | Yes, after auth hardening | Use `by_category`, `top_merchants`, `monthly`, `insights`. |
| `get_transactions` | CATEGORY_ANALYSIS | `GET /api/transactions` | Spectra | Read | `transactions.read_detail` | No | Yes, bounded | Limit rows and require stronger consent than summary. |
| `get_uncategorized_transactions` | CATEGORY_CORRECTION | `GET /api/transactions?uncategorized_only=true` | Spectra | Read | `transactions.read_detail` | No | Yes, bounded | Good for category review workflows. |
| `get_anomalies` | ANOMALY_EXPLANATION | `GET /anomalies` | Bank Simulator | Read | `anomaly.read` | No | Yes, if bank-linked | No Spectra-native anomaly endpoint exists. |
| `get_balance_prediction` | FORECAST_BALANCE | `GET /prediction` | Bank Simulator | Read | `forecast.read` and `account.read_balance` | No | Yes, if bank-linked | Contains current and predicted balance. |
| `get_category_options` | CATEGORY_CORRECTION | `GET /api/categories/options` | Spectra | Read | `categories.read` | No | Yes, after auth hardening | First safe category helper. |
| `update_transaction_category` | CATEGORY_CORRECTION | `PATCH /api/transactions/{tx_id}` | Spectra | Write | `category.update` | Yes | No for first MVP | Needs ownership checks, confirmation, and audit log. |
| `bulk_update_transaction_category` | CATEGORY_CORRECTION | `POST /api/transactions/bulk-category` | Spectra | Write | `category.update` | Yes | No for first MVP | High impact write. |
| `get_category_rules` | CATEGORY_CORRECTION | `GET /api/settings/rules` | Spectra | Read | `rules.read` | No | Maybe | Rules appear global and unauthenticated. |
| `create_category_rule` | CATEGORY_CORRECTION | `POST /api/settings/rules` | Spectra | Write | `rules.write` | Yes | No | Needs confirmation and audit. |
| `test_category_rule` | CATEGORY_CORRECTION | `POST /api/settings/rules/test` | Spectra | Read/test | `rules.read` | No | Maybe | Keep examples bounded/redacted. |
| `get_learning_summary` | CATEGORY_CORRECTION | `GET /api/settings/learning` | Spectra | Read | `memory.read` | No | Maybe | Can expose merchant/category history; harden first. |
| `get_budget_status` | SAVING_SUGGESTION, FINANCIAL_HEALTH_SCORE | `GET /api/budget` | Spectra | Read | `budget.read` | No | Yes, after auth hardening | Good optional read-only tool. |
| `update_budget_limit` | SAVING_SUGGESTION | `PATCH /api/budget/{category}` | Spectra | Write | `budget.write` | Yes | No for first MVP | Needs confirmation. |
| `get_trends` | SAVING_SUGGESTION, CATEGORY_ANALYSIS | `GET /api/trends` | Spectra | Read | `trends.read` | No | Yes, after auth hardening | Good optional read-only tool. |
| `get_subscriptions` | SAVING_SUGGESTION | `GET /api/subscriptions` | Spectra | Read | `subscriptions.read` | No | Yes, after auth hardening | Sensitive merchants and recurring spend. |
| `get_financial_health_score` | FINANCIAL_HEALTH_SCORE | Missing | Spectra | Read | `financial_health.read` | No | No | Needs new endpoint/service. Can compose summary, budget, trends, subscriptions, forecast, anomalies. |
| No tool | GENERAL_FINANCE_ADVICE | No endpoint required | LLM-only | Read | `public.read` | No | Yes | Must avoid personalized claims unless tools are called. |
| No tool | PRIVACY_OR_PERMISSION | Missing consent/permission APIs | Spectra | Read | `session.read` | No | Partial | Needs permission service and consent APIs. |
| No tool | OUT_OF_SCOPE_INVESTMENT_ADVICE | No endpoint required | LLM policy response | Read | `public.read` | No | Yes | Should refuse regulated/specific investment advice. |

## 4. Permission Scope Proposal

| Scope | Meaning | Related Tools | Sensitive? | Default Granted? | Notes |
|---|---|---|---|---|---|
| `public.read` | Non-user-specific public info. | General finance advice, health checks. | No | Yes | No personal data. |
| `session.read` | Read session state. | `get_current_user`. | Medium | Yes after login | Should require authenticated session. |
| `analytics.read` | Read aggregate spending/income analytics. | `get_account_summary`, `get_spending_breakdown`. | Medium | Yes after login | Safer than raw transaction detail. |
| `transactions.read_summary` | Read bounded transaction summaries without full details. | Future reduced `get_transactions` variant. | Medium | Yes after login | Prefer for MVP. |
| `transactions.read_detail` | Read raw transaction rows and merchant names. | `get_transactions`, `get_uncategorized_transactions`, bank `get_transactions`. | High | Maybe | Require explicit consent or strong default notice. |
| `account.read_basic` | Read user profile/basic account identity. | `get_current_user`. | Medium | Yes after login | Avoid leaking account numbers unless needed. |
| `account.read_balance` | Read current/predicted balances. | `get_balance_prediction`. | High | No by default | Balance is highly sensitive. |
| `categories.read` | Read available categories. | `get_category_options`. | Low | Yes after login | Mostly safe. |
| `category.update` | Update transaction merchant/category. | `update_transaction_category`, `bulk_update_transaction_category`. | High | No | Always require confirmation and audit. |
| `rules.read` | Read/test category rules. | `get_category_rules`, `test_category_rule`. | Medium | Maybe | Rules can reveal user behavior. |
| `rules.write` | Create/update/delete category rules. | `create_category_rule`, update/delete rule tools. | High | No | Always require confirmation. |
| `memory.read` | Read learning feedback/memory. | `get_learning_summary`. | High | No by default | Can expose historical user corrections. |
| `memory.write` | Modify/reapply learning/memory. | `learning_reapply`, import confirm. | High | No | Requires confirmation. |
| `budget.read` | Read budget limits/status. | `get_budget_status`. | Medium | Yes after login | Good for savings suggestions. |
| `budget.write` | Modify budget limits. | `update_budget_limit`. | High | No | Requires confirmation. |
| `trends.read` | Read trends and yearly/monthly analytics. | `get_trends`. | Medium | Yes after login | Aggregate but still personal. |
| `subscriptions.read` | Read recurring merchants and charges. | `get_subscriptions`. | High | Maybe | Recurring merchants are sensitive. |
| `forecast.read` | Read forecasts and prediction outputs. | `get_balance_prediction`. | High | Maybe | Often includes balance. |
| `anomaly.read` | Read anomalous transactions. | `get_anomalies`. | High | Maybe | Exposes raw merchants/amounts/reasons. |
| `financial_health.read` | Read composed financial health score. | `get_financial_health_score`. | High | No until implemented | Must explain methodology. |
| `admin.read` | Read system-wide users/stats. | Bank `/users`, `/stats`. | High | No | Normal chatbot users must not receive this. |
| `admin.write` | Administrative writes. | None safe for chatbot. | Critical | No | Do not grant to normal users. |
| `destructive.write` | Destructive actions. | `POST /api/settings/reset-db`. | Critical | No | Must never be registered as chatbot tool. |

The LLM supervisor must never access the database directly. It should call only allowlisted tools through a permission-aware executor.

## 5. Missing Components For Chatbot v3

| Missing Component | Why Needed | Suggested File/Module | Priority | Notes |
|---|---|---|---|---|
| `/api/chat` endpoint | Main chatbot entrypoint. | `src/spectra/web/chat_routes.py` or `src/spectra/web/server.py` include. | P0 | Not found. |
| Chat request/response models | Stable API contract for user messages, tool calls, citations, and Vietnamese answer text. | `src/spectra/chat/models.py` | P0 | Not found. |
| Chat session table | Persist chat sessions per user. | `supabase/migrations/0004_chatbot_v3.sql` | P0 | Not found. |
| Chat message table | Store user/assistant messages. | `supabase/migrations/0004_chatbot_v3.sql` | P0 | Not found. |
| Chat tool call log table | Trace tool calls and outputs. | `supabase/migrations/0004_chatbot_v3.sql` | P0 | Not found. |
| User consent table | Persist consent grants for sensitive tools. | `supabase/migrations/0004_chatbot_v3.sql` | P0 | Not found. |
| Consent API | Grant/revoke/list tool consent. | `src/spectra/chat/consent.py`, `src/spectra/web/chat_routes.py` | P0 | Existing Bank SSO consent is not enough. |
| Permission service | Central scope checks before tool execution. | `src/spectra/chat/permissions.py` | P0 | Not found. |
| Tool registry | Define tool metadata, scopes, input schemas, confirmation requirements. | `src/spectra/chat/tools/registry.py` | P0 | Not found. |
| Tool executor | Executes allowlisted tools with auth, validation, redaction, logging. | `src/spectra/chat/tools/executor.py` | P0 | Not found. |
| LLM supervisor service | Vietnamese intent understanding, routing, tool selection, final response synthesis. | `src/spectra/chat/supervisor.py` | P1 | Not found. |
| Masking/redaction service | Prevent account numbers, excessive raw transactions, secrets, and logs from leaking. | `src/spectra/chat/redaction.py` | P0 | Not found. |
| Audit log service | Security trace for chat/tool/write actions. | `src/spectra/chat/audit.py` | P0 | Not found. |
| Financial health score service | Compute explainable score from existing metrics. | `src/spectra/financial_health.py` | P1 | Not found. |
| Spectra-native anomaly API | Use anomalies without Bank Simulator dependency. | `src/spectra/anomalies.py`, `/api/anomalies` | P2 | Not found. |
| Spectra-native forecast API | Forecast balance/cashflow from Spectra history. | `src/spectra/forecast.py`, `/api/forecast` | P2 | Not found. |
| Tests for supervisor routing | Verify intent routing, permission checks, confirmation gates. | `tests/test_chatbot_*.py` | P0 | Not found. |

## 6. Security / Privacy Risks

| Risk | File/Endpoint | Severity | Why It Matters | Recommended Fix |
|---|---|---|---|---|
| User-data APIs silently use empty user id. | `GET /api/summary` at `src/spectra/web/server.py:829`; `GET /api/transactions` at line 987; `GET /api/budget` at line 2082; `GET /api/trends` at line 2171; `GET /api/subscriptions` at line 2251. | HIGH | Missing session can look like empty data, hiding auth failures from chatbot logic. | Require authenticated session and return 401 before tool exposure. |
| Several settings/rules/learning endpoints lack explicit session checks. | `/api/settings`, `/api/settings/rules*`, `/api/settings/learning`, `/api/settings/reset-db`. | HIGH | LLM tools could expose or mutate global settings/rules/memory without user auth. | Add auth middleware/dependency and per-scope checks. |
| Destructive reset endpoint exists. | `POST /api/settings/reset-db` at `src/spectra/web/server.py:1459`. | CRITICAL | Deletes data and currently only checks body token `RESET`. | Never register as chatbot tool; require admin auth and CSRF/confirmation outside chat. |
| Public demo/admin endpoints expose user/system info. | `GET /api/auth/demo-users`, Bank `GET /users`, Bank `GET /stats`. | HIGH | Can expose account numbers, balances, and system-wide stats. | Restrict to admin/dev mode; never expose to normal chatbot. |
| Write endpoints have no chatbot confirmation layer. | `PATCH /api/transactions/{tx_id}`, bulk category, rules writes, budget writes, learning reapply, import confirm. | HIGH | LLM could mutate user data accidentally or after prompt injection. | Tool executor must require explicit user confirmation and audit log. |
| Raw transaction detail exposure. | `GET /api/transactions`, Bank `GET /transactions`. | HIGH | Merchants, dates, amounts, account ids, balances are sensitive. | Bound result size, redact where possible, separate summary/detail scopes. |
| Bank account number and balances exposed. | Bank `/me`, `/users`, `/prediction`. | HIGH | Account numbers and balances are highly sensitive. | Mask account numbers; require `account.read_balance` for balances. |
| Missing masking/redaction service. | Chatbot architecture missing. | HIGH | Tool outputs may be copied verbatim into prompts and logs. | Add redaction before LLM context and audit logs. |
| Missing audit logs. | Chatbot architecture missing. | HIGH | No trace of LLM actions, tool calls, or consent decisions. | Add chat/tool/audit tables and service. |
| LLM over-fetching risk. | Any detail endpoint registered as a tool. | MEDIUM | Supervisor may request more transactions than needed. | Define max limits and tool-level input validation. |
| Duplicate Spectra page routes. | `/transactions`, `/upload`, `/settings` in `src/spectra/web/server.py:777`, `784`, `791`, `800`, `807`, `814`. | LOW | Route duplication can confuse audits and future route changes. | Clean up separately after Phase 1 if desired. |
| `/settings` page handler returns before auth redirect. | `src/spectra/web/server.py:791`. | MEDIUM | Settings UI may be reachable without the intended setup redirect. | Add explicit auth/setup checks. |

## 7. Recommended Phase 2 Inputs

### APIs That Can Be Immediately Wrapped As Read Tools After Auth Hardening

- `GET /api/auth/me`
- `GET /api/summary`
- `GET /api/transactions`
- `GET /api/categories/options`
- `GET /api/budget`
- `GET /api/trends`
- `GET /api/subscriptions`
- `GET /api/settings/learning`
- Bank `GET /summary`
- Bank `GET /anomalies`
- Bank `GET /prediction`

### APIs That Must Be Protected Before Tool Exposure

- `GET /api/summary`
- `GET /api/transactions`
- `GET /api/categories/options`
- `GET /api/settings`
- `GET /api/settings/rules`
- `POST /api/settings/rules/test`
- `GET /api/settings/learning`
- `GET /api/budget`
- `GET /api/trends`
- `GET /api/subscriptions`
- All write endpoints listed below.

### New Tables Needed

- `app_chat_sessions`
- `app_chat_messages`
- `app_chat_tool_calls`
- `app_chat_user_consents`
- `app_chat_audit_log`

### New Modules Needed

- `src/spectra/chat/models.py`
- `src/spectra/chat/permissions.py`
- `src/spectra/chat/consent.py`
- `src/spectra/chat/tools/registry.py`
- `src/spectra/chat/tools/executor.py`
- `src/spectra/chat/supervisor.py`
- `src/spectra/chat/redaction.py`
- `src/spectra/chat/audit.py`
- `src/spectra/financial_health.py`

### First 4 Safe Read-Only Tools

1. `get_current_user` from `GET /api/auth/me`
2. `get_account_summary` from `GET /api/summary`
3. `get_transactions` from `GET /api/transactions` with strict row limits
4. `get_category_options` from `GET /api/categories/options`

### Optional Read-Only Tools

5. `get_budget_status` from `GET /api/budget`
6. `get_trends` from `GET /api/trends`
7. `get_subscriptions` from `GET /api/subscriptions`
8. `get_learning_summary` from `GET /api/settings/learning`

### High-Risk Tools That Must Wait

- `update_transaction_category`
- `bulk_update_transaction_category`
- `create_category_rule`
- `update_category_rule`
- `delete_category_rule`
- `update_budget_limit`
- `learning_reapply`
- `confirm_import`
- `reset_db`

### Endpoints That Must Never Be Exposed To The Chatbot

- `POST /api/settings/reset-db`
- Bank `GET /users` for normal users
- Bank `GET /stats` for normal users
- `GET /api/auth/demo-users` for normal users
- Auth login/logout/SSO callback endpoints as LLM tools
- HTML page routes

## 8. Output Requirements

This file is written to `docs/chatbot-api-inventory.md`.

It lists all discovered FastAPI route declarations from `bank_simulator/main.py` and `src/spectra/web/server.py`, maps current endpoints to chatbot tool candidates, proposes permission scopes, identifies missing chatbot v3 components, documents security/privacy risks, and gives a Phase 2 checklist.

## 9. Acceptance Criteria Status

| Criterion | Status |
|---|---|
| `docs/chatbot-api-inventory.md` exists. | Complete |
| Lists all discovered FastAPI routes. | Complete |
| Maps existing endpoints to chatbot tool candidates. | Complete |
| Identifies tools safe for MVP. | Complete |
| Identifies tools requiring confirmation. | Complete |
| Identifies endpoints never exposed to LLM supervisor. | Complete |
| Proposes permission scopes. | Complete |
| Lists missing chatbot v3 components. | Complete |
| Lists security/privacy risks. | Complete |
| Gives clear Phase 2 checklist. | Complete |
| No application logic changed. | Complete |
| Existing tests still pass if run. | Not run in this documentation-only phase. |

## Audit Counts

- FastAPI route declarations found: 51 total.
- Chatbot tool candidates identified: 24 total, including read, write, maybe, and missing-tool candidates.
- Missing chatbot v3 components listed: 17.
- Recommended first Phase 2 tools: `get_current_user`, `get_account_summary`, `get_transactions`, `get_category_options`.
