# Spectra — Project Map & System Design (Orientation Guide)

> **Mục đích của file này:** Đây là tài liệu định hướng (orientation) dành cho cả người mới và cho AI assistant.
> Khi cần chỉnh sửa / thêm tính năng, **đọc file này trước** để biết *chỗ nào làm gì*, rồi mở đúng file cần thiết —
> tránh quét lại toàn bộ repo (tiết kiệm thời gian và token).
>
> Tài liệu chi tiết về DB schema, guardrails, confirmation flow: xem [`technical_design_document.md`](technical_design_document.md).
> File này tập trung vào **"map"**: vị trí code, trách nhiệm từng module, và "muốn sửa X thì vào đâu".
>
> _Cập nhật lần cuối: 2026-06-27. Nếu sửa cấu trúc lớn, hãy cập nhật lại file này._

---

## 1. Tóm tắt hệ thống (1 phút)

Spectra = **dashboard quản lý tài chính cá nhân + AI chatbot tiếng Việt**.

- **Backend:** FastAPI (Python 3.11+), entrypoint `spectra --serve`.
- **Frontend:** React + Vite (thư mục `frontend/`), build ra `src/spectra/web/dist/`.
- **Database:** PostgreSQL / Supabase, truy cập qua `DATABASE_URL` (psycopg3). Tất cả bảng app dùng prefix `app_`.
- **Bank Simulator:** service riêng (`bank_simulator/`, FastAPI, cổng 8000) — ngân hàng giả lập cấp SSO + dữ liệu giao dịch demo. Dùng chung DB.
- **LLM:** OpenAI (mặc định chat) / Gemini / local. Cấu hình qua `AI_PROVIDER`.

```
React (frontend/) ──HTTP+cookie──► FastAPI (src/spectra/web/server.py)
                                       ├─► PostgreSQL/Supabase (src/spectra/db.py)
                                       ├─► OpenAI/Gemini LLM (src/spectra/chat/, src/spectra/ai.py)
                                       └─► Bank Simulator REST (bank_simulator/, cổng 8000)
```

Hai cổng chính: **Spectra** `8080/8081`, **Bank Simulator** `8000`.

---

## 2. Bản đồ thư mục (chỗ nào làm gì)

| Đường dẫn | Trách nhiệm |
| :--- | :--- |
| `src/spectra/web/server.py` | **Toàn bộ FastAPI routes** (~2900 dòng). Auth, chat, transactions, budget, savings, upload, SSO. Xem mục 4. |
| `src/spectra/chat/` | **Chatbot engine** (supervisor, tools, guardrails, confirmation, memory). Xem mục 5. |
| `src/spectra/db.py` | Lớp truy cập DB. Connection pool psycopg3, helper query, adapter SQLite→Postgres syntax. |
| `src/spectra/config.py` | `Settings` (pydantic-settings). Mọi env var / `.env` đọc ở đây. `load_settings()` cache. |
| `src/spectra/pipeline.py` | CLI entrypoint (`spectra` command). `--serve` để chạy web; cũng chạy import batch. |
| `src/spectra/ai.py` | Categorization bằng LLM (provider-agnostic wrapper Gemini/OpenAI). |
| `src/spectra/local_categorizer.py` | Phân loại merchant không cần LLM (rule + fuzzy). |
| `src/spectra/ml_classifier.py` | Phân loại bằng scikit-learn (học từ feedback). |
| `src/spectra/csv_parser.py` / `pdf_parser.py` / `ofx_parser.py` | Parse file sao kê import (CSV / PDF / OFX). |
| `src/spectra/budget.py` / `budget_planner.py` | Tính trạng thái ngân sách + đề xuất/what-if plan. |
| `src/spectra/savings_goals.py` | Logic mục tiêu tiết kiệm (feasibility, monthly required). |
| `src/spectra/financial_health.py` | Tính điểm sức khỏe tài chính. |
| `src/spectra/recurring.py` | Phát hiện giao dịch định kỳ / subscription. |
| `src/spectra/trends.py` / `dashboard.py` / `reporter.py` | Tổng hợp số liệu cho dashboard / trends / report. |
| `src/spectra/cycles.py` | Tính chu kỳ ngân sách (billing cycle). |
| `src/spectra/categories.py` | Danh mục chi tiêu chuẩn (tiếng Việt). |
| `src/spectra/rules.py` | Áp dụng category rules người dùng định nghĩa. |
| `src/spectra/fx.py` | Quy đổi ngoại tệ. |
| `src/spectra/sheets.py` | Tích hợp Google Sheets (legacy/optional). |
| `src/spectra/web/templates/` | Jinja2 templates (bản server-rendered cũ). |
| `src/spectra/web/dist/` | **Bundle React đã build** (production frontend được serve từ đây). |
| `frontend/src/` | Source React (xem mục 6). |
| `bank_simulator/` | Service ngân hàng giả lập riêng (FastAPI). `main.py`, `data_seeder.py`. |
| `supabase/migrations/` | SQL migrations — **nguồn chân lý cho DB schema** (xem mục 3). |
| `tests/chatbot/` | Test suite (chủ yếu cho chatbot). `uv run pytest`. |
| `docs/` | Tài liệu (PRD, technical design, phase docs, eval metrics). |
| `scratch/` | Script tạm/debug, KHÔNG phải code production. |
| `inbox/` / `processed/` | Thư mục import file sao kê (chờ xử lý / đã xử lý). |

---

## 3. Database (nguồn chân lý: `supabase/migrations/`)

Tất cả bảng app dùng prefix `app_`. Bảng `bank_*` thuộc Bank Simulator. Multi-tenant qua cột `user_id`.

| Migration | Bảng tạo |
| :--- | :--- |
| `0001_initial_schema.sql` | `app_seen_transactions`, `app_tx_history`, `app_user_overrides`, `app_merchant_categories`, `app_budget_limits`, `app_settings`, `app_category_rules`, `app_learning_feedback` |
| `0002_bank_simulator_schema.sql` | `bank_accounts`, `bank_transactions`, `user_personas`, `transaction_patterns` |
| `0003_bank_user_credentials.sql` | `bank_user_credentials` |
| `0004_chat_history_memory.sql` | `app_chat_sessions`, `app_chat_messages`, `app_chat_tool_calls`, `app_user_memories` |
| `0005_mvp_ai_assistant_hardening.sql` | `app_savings_goals`, `app_chat_feedback`, `app_chat_pending_confirmations`, `app_chat_audit_log` |

**Bảng quan trọng nhất:**
- `app_tx_history` — giao dịch người dùng (date, clean_name, amount, category, original_description).
- `app_chat_sessions` / `app_chat_messages` — lịch sử chat.
- `app_chat_pending_confirmations` — hành động write chờ duyệt (confirmation flow).
- `app_user_memories` — bộ nhớ cá nhân hóa chatbot.
- `app_savings_goals` — mục tiêu tiết kiệm.

Chi tiết cột: xem [`technical_design_document.md`](technical_design_document.md) mục 2.

---

## 4. API Endpoints (`src/spectra/web/server.py`)

Mọi route nằm trong 1 file. Dùng dòng tham chiếu dưới đây để nhảy thẳng.

**Auth & SSO**
- `GET /api/auth/me` (server.py:721), `GET /api/auth/current-context` (734), `GET /api/auth/demo-users` (770)
- `POST /api/auth/login` (775), `POST /api/auth/logout` (789)
- `GET /sso/bank` (1115), `GET /sso/bank/callback` (1126)

**Chatbot**
- `POST /api/chat` (797) — entrypoint chính, gọi `ChatSupervisor`.
- `GET /api/chat/sessions` (863), `GET /api/chat/sessions/{id}/messages` (873)
- `POST /api/chat/sessions/{id}/archive` (886), `DELETE /api/chat/sessions/{id}` (899)
- `GET /api/chat/memories` (912), `DELETE /api/chat/memories/{id}` (922)
- `POST /api/chat/feedback` (935)
- `POST /api/confirm` (2452) — duyệt/hủy hành động write chờ xác nhận.

**Transactions & Categories**
- `GET /api/transactions` (1407), `PATCH /api/transactions/{tx_id}` (1498)
- `POST /api/transactions/bulk-category` (1553)
- `GET /api/categories` (1603), `GET /api/categories/options` (1619)
- `GET /api/summary` (1180)

**Budget & Trends**
- `GET /api/budget` (2565), `PATCH /api/budget/{category}` (2702)
- `GET /api/budget/recommendation` (2639), `POST /api/budget/simulate` (2666), `POST /api/budget/plan` (2689)
- `GET /api/trends` (2721), `GET /api/subscriptions` (2803)

**Savings Goals**
- `GET /api/savings-goals` (1024), `POST /api/savings-goals` (1076)
- `POST /api/savings-goals/plan` (1034), `POST /api/savings-goals/simulate` (1055)
- `PATCH /api/savings-goals/{id}` (1089), `POST /api/savings-goals/{id}/archive` (1102)
- `GET /api/financial-health-score` (966)

**Settings & Import**
- `GET /api/settings` (1637), `PATCH /api/settings/preferences` (1677)
- Rules: `GET/POST /api/settings/rules` (1753/1772), `PATCH/DELETE .../{id}` (1807/1876), `POST .../test` (1838)
- `GET /api/settings/learning` (1889), `POST /api/settings/learning/reapply` (1922)
- `POST /api/settings/reset-db` (1933) — **chỉ admin/debug, KHÔNG expose cho chatbot.**
- `POST /api/import-bank` (2176), `POST /api/upload` (2216)

---

## 5. Chatbot Engine (`src/spectra/chat/`)

Đây là phần phức tạp nhất. Kiến trúc: **Supervisor Agent + allowlisted tools + guardrails + 2-step confirmation**.

| File | Trách nhiệm |
| :--- | :--- |
| `supervisor.py` (~2456L) | **`ChatSupervisor`** — bộ não điều phối. Deterministic regex routing → tool → finalizer. Có hàng loạt `_is_*_question`, `_parse_*`, `_format_*_answer`. |
| `tools.py` (469L) | **Tool registry** (allowlist). `get_registered_tools()`, `openai_tool_definitions()`. Khai báo schema + permission từng tool. |
| `executor.py` (795L) | **`ToolExecutor`** — chạy tool thực tế, kiểm tra quyền, tạo pending confirmation cho write tool, cache, timeout. |
| `finance_tools.py` | Service read-only: anomaly, balance forecast. |
| `insight_tools.py` (728L) | Insight read-only deterministic: recurring, compare period, budget overrun, cashflow calendar, purchase impact, debt, emergency fund. |
| `confirmation.py` | Pending confirmation store (CRUD bảng `app_chat_pending_confirmations`, expiry 10 phút). |
| `guardrails/` | Engine an toàn nhiều lớp (xem dưới). |
| `memory.py` | Bộ nhớ user/session an toàn (`app_user_memories`). |
| `history.py` | Lưu session/message/tool-call (`app_chat_*`). |
| `context.py` | Build context gọn cho prompt. |
| `prompts.py` | System prompt cho supervisor + finalizer. |
| `redaction.py` | Che dữ liệu nhạy cảm trong payload tool. |
| `audit.py` | Audit log write tool đã confirm (`app_chat_audit_log`). |
| `tracing.py` | Tracing phân cấp + structured JSON log cho LLM/tool. |
| `evaluation.py` / `eval_judge.py` | Chạy regression + LLM-as-a-Judge eval từ dataset trong docs. |
| `models.py` | Pydantic models (`ChatRequest`, `ChatResponse`, ...). |

**Guardrails (`src/spectra/chat/guardrails/`):**
- `input_guards.py` — PromptInjection, OutOfScope, InvestmentAdvice, SensitiveData.
- `tool_guards.py` — UnregisteredTool, **Scope** (enforce `required_scope`, fail-closed), ToolParameter (clamp limit/days), WriteConfirmation.
- `scopes.py` — chính sách quyền: `resolve_granted_scopes(user_id)` (policy hook để siết theo user/role) + `DEFAULT_AUTHENTICATED_SCOPES`.
- `output_guards.py` — CredentialLeak, PIILeak, DisclaimerEnforcer.
- `rules.py` / `engine.py` — định nghĩa + orchestration (thứ tự tool guard: Unregistered → Scope → Parameter → WriteConfirmation).

**Các tool đã đăng ký (tools.py):** `get_current_user`, `get_account_summary`, `get_transactions`, `search`,
`get_category_options`, `update_transaction_category` (write), `create_category_rule` (write), `get_category_rules`,
`get_learning_summary`, `get_anomalies`, `get_balance_forecast`, `explain_anomaly`, `get_financial_health_score`,
`get_savings_goals`, `create_savings_goal` (write), `update_savings_goal` (write), `simulate_savings_adjustment`,
`get_budget_status`, `recommend_budget_plan`, `simulate_budget_adjustment`, `compare_budget_vs_actual`,
`update_budget_limit` (write), `upsert_budget_plan` (write), + các insight tool (recurring, compare period,
budget overrun, cashflow calendar, purchase impact, debt, emergency fund).

**Luồng 1 request chat (LangGraph):**
`POST /api/chat` → `input_guard` → `confirmation` → `deterministic` (phase3 category) → `fast_path` (regex routes; **bỏ qua nếu câu đa-ý** `_is_multi_intent`) → `planner` (LLM tách câu ghép thành nhiều task có `depends_on`/`$ref`) → `executor` (write tool → pending confirmation) → `synthesis` (gộp nhiều tool result bằng LLM) → `finalizer` (chỉ cho câu đơn; câu đa-ý bỏ qua để tiết kiệm 1 LLM call) → `output_guard`.

**Câu hỏi nhiều ý (multi-intent):** 1 câu lớn gồm nhiều ý nhỏ được planner tách thành nhiều task → mỗi task 1 tool → `synthesis` trả lời lần lượt từng ý. Heuristic `_is_multi_intent` (≥2 nhóm chủ đề khác nhau hoặc ≥2 dấu "?") chặn fast-path "ăn" mất các ý còn lại. Phạm vi hiện tại: read-only (ý ghi tách confirmation riêng).

---

## 6. Frontend (`frontend/src/`)

React + Vite. Build vào `src/spectra/web/dist/` để backend serve.

| Đường dẫn | Vai trò |
| :--- | :--- |
| `api/client.js` | HTTP client (fetch + cookie). |
| `api/services.js` | Wrapper gọi từng endpoint backend. |
| `context/AppContext.jsx` | Global state. |
| `hooks/useSSE.js` | Stream phản hồi chat (Server-Sent Events). |
| `components/chat/ChatPanel.jsx` | Khung chat + confirmation card. |
| `components/layout/` | Layout, Sidebar. |
| `pages/` | `Dashboard`, `Transactions`, `Budget`, `Trends`, `Subscriptions`, `Upload`, `Settings`, `Login`. |

Build: `cd frontend && npm run build`. Dev: `npm run dev`.

---

## 7. Cấu hình & chạy

**Env vars chính** (`src/spectra/config.py`, file `.env` ở root):
- `DATABASE_URL` (bắt buộc) — Postgres/Supabase.
- `AI_PROVIDER` = `openai` | `gemini` | `local`; `OPENAI_API_KEY` / `GEMINI_API_KEY`.
- `OPENAI_MODEL` (mặc định `gpt-4o-mini`), `CHAT_FINALIZER_ENABLED`.
- `BANK_SIMULATOR_BASE_URL` (mặc định `http://localhost:8000`), `SPECTRA_BASE_URL`.
- `SSO_SHARED_SECRET`, `SESSION_TTL_SECONDS`, `SSO_TOKEN_TTL_SECONDS`.
- Observability: `LANGSMITH_API_KEY`, `OTEL_EXPORTER_OTLP_ENDPOINT`.

**Lệnh hay dùng:**
```bash
uv sync                              # cài deps
uv run spectra --serve --port 8080   # chạy backend
cd bank_simulator && python main.py  # chạy bank simulator (cổng 8000)
cd frontend && npm run dev           # frontend dev
cd frontend && npm run build         # build frontend vào dist/
uv run pytest -q                     # test backend
uv run pytest tests/chatbot -v       # test chatbot
uv run spectra-chat-eval             # chạy eval chatbot
```

---

## 8. "Muốn sửa X thì vào đâu" (cheat sheet)

| Muốn làm | Vào file |
| :--- | :--- |
| Thêm/sửa API endpoint | `src/spectra/web/server.py` |
| Thêm tool mới cho chatbot | `chat/tools.py` (schema+permission) → `chat/executor.py` (handler) → `chat/supervisor.py` (routing/format nếu cần) |
| Sửa logic định tuyến câu hỏi tiếng Việt | `chat/supervisor.py` — các hàm `_is_*_question`, `_parse_*` |
| Sửa câu trả lời chatbot (wording) | `chat/supervisor.py` `_format_*_answer` + `chat/prompts.py` |
| Sửa guardrails / bảo mật chat | `chat/guardrails/*.py` |
| Sửa confirmation flow (write tool) | `chat/confirmation.py` + `chat/executor.py` + `POST /api/confirm` (server.py:2452) |
| Đổi schema DB | Thêm migration mới trong `supabase/migrations/` |
| Sửa parsing file import | `csv_parser.py` / `pdf_parser.py` / `ofx_parser.py` |
| Sửa logic phân loại giao dịch | `ai.py` (LLM) / `local_categorizer.py` (rule) / `ml_classifier.py` (ML) |
| Sửa ngân sách / mục tiêu / sức khỏe TC | `budget.py`, `budget_planner.py`, `savings_goals.py`, `financial_health.py` |
| Sửa UI | `frontend/src/pages/` hoặc `frontend/src/components/` |
| Đổi config/env | `src/spectra/config.py` + `.env` |
| Sửa Bank Simulator | `bank_simulator/main.py`, `bank_simulator/data_seeder.py` |

---

## 9. Quy ước & lưu ý an toàn

- **Reset DB / admin endpoints KHÔNG được expose như chatbot tool.**
- **Mọi write tool BẮT BUỘC qua confirmation flow** (không chạy trực tiếp).
- Chatbot chỉ dùng **allowlisted tools** trong `chat/tools.py`.
- Output luôn qua output guards (ẩn `sk-...`, số tài khoản, tên hàm backend, UUID).
- Demo auth = session cookie local, chưa phải mô hình SaaS production.
- DB syntax viết kiểu SQLite-ish nhưng `db.py` tự convert sang Postgres (`_to_postgres_sql`).
- `scratch/` là script tạm — đừng coi là code chính.

---

## 10. Known gaps / Tech debt (đánh giá 2026-06-27)

Kết quả review phần tools & kiến trúc AI. Sửa theo thứ tự ưu tiên.

| # | Vấn đề | Trạng thái | Vị trí |
| :--- | :--- | :--- | :--- |
| 1 | `required_scope` chỉ là metadata, không enforce | ✅ **Đã sửa** — thêm `ScopeGuard` fail-closed | `guardrails/scopes.py`, `guardrails/tool_guards.py` |
| 2 | Rate limit cho `/api/chat` (mỗi request gọi LLM = tốn tiền) | ⬜ Chưa làm | `web/server.py:797` |
| 3 | Layering inversion: `executor.py` import `spectra.web.server` 35+ lần, gọi route handler. Nên tách service layer dùng chung cho web + chat | ⬜ Chưa làm | `chat/executor.py` |
| 4 | Dispatch tool bằng if/elif 35 nhánh → nên dict/`getattr` | ⬜ Chưa làm | `chat/executor.py:183-256` |
| 5 | `server.py` (2937L) và `supervisor.py` (2456L) monolith → tách theo `APIRouter` / module | ⬜ Chưa làm | `web/server.py`, `chat/supervisor.py` |
| 6 | Routing tiếng Việt bằng regex thủ công, brittle | ⬜ Để sau (đang chạy được) | `chat/supervisor.py` `_is_*_question` |
| 7 | Upload/save chậm: delay giả 5s + `is_seen` per-row + ~3N commit khi confirm + ghi trùng | ✅ **Đã tối ưu** — bỏ sleep giả, batch `get_seen_ids`, `record_learning_feedback_batch`, bỏ ghi trùng | `web/server.py` `_stream_processed_transactions` & `api_confirm`, `db.py` |

**Lưu ý import (tech debt còn lại):** ✅ Đã xoá khối dead code (~160 dòng) trong `/api/upload`; xử lý thật chỉ còn trong `_stream_processed_transactions`. Còn lại: `categorise()` (cloud AI) chạy blocking trong async generator → có thể bọc `run_in_executor` để stream mượt hơn, nhưng không phải nguyên nhân chậm chính.

**Điểm mạnh hiện có (đừng phá):** allowlist tool registry + JSON Schema clamp, confirmation 2 bước cho write, guardrails nhiều lớp, audit log, eval harness (`eval_judge.py`), tracing LangSmith/OTel, cache + retry + timeout cho tool.

---

## 11. Tài liệu liên quan trong `docs/`

- [`technical_design_document.md`](technical_design_document.md) — TDD đầy đủ (schema chi tiết, guardrails, confirmation, mermaid diagrams).
- [`prd.md`](prd.md) — yêu cầu sản phẩm.
- [`chatbot-api-inventory.md`](chatbot-api-inventory.md) — inventory API chatbot.
- [`chatbot-evaluation*.md`](chatbot-evaluation.md), [`evaluation_report.md`](evaluation_report.md) — đánh giá chatbot.
- `chatbot-phase-*.md` — lịch sử phát triển theo phase.
- `flow_diagrams/` — sơ đồ luồng (PNG).
</content>
</invoke>
