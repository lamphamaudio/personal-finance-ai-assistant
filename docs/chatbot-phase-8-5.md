# Chatbot Phase 8.5 Persistent History And Memory

## What Phase 8.5 Adds

Phase 8.5 adds backend persistence for chatbot sessions, messages, tool-call traces, compact conversation context, and safe user memory.

Implemented:

- Persisted chat sessions per authenticated user.
- Persisted user and assistant messages.
- Structured persisted chat tool-call traces.
- `/api/chat` returns backend `session_id` and assistant `message_id`.
- `/api/chat` can continue an existing session.
- Recent conversation retrieval for supervisor context.
- Context builder in `src/spectra/chat/context.py`.
- User/session memory service in `src/spectra/chat/memory.py`.
- Chat history service in `src/spectra/chat/history.py`.
- Safe memory read/delete APIs.
- Memory tools: `get_conversation_context`, `get_user_memories`, `remember_user_preference`, `forget_user_memory`.
- Session state persistence for last goal plan, last budget plan, and last transaction candidates.
- Redaction before saving messages, metadata, and tool-call payloads.
- Frontend chat panel now adopts the backend-created `session_id`.

Not implemented:

- Vector database.
- Complex RAG.
- Cross-user memory.
- Admin memory dashboard.
- Long-term storage of raw financial data.
- Persistent pending confirmations. Existing pending confirmations are still process-local.

## Chat History Vs Memory

Chat history stores the transcript: sessions, user messages, assistant messages, and tool-call traces.

Memory stores compact facts used for continuity:

- Short-term conversation context: last 12 recent messages in the current session.
- Session memory: last goal plan, budget plan, and transaction candidates for follow-up references.
- Long-term user memory: confirmed preferences and safe stable facts.
- Financial state memory: references only. Current financial data must still come from tools.

Old chat history and memories are not treated as current financial truth.

## Database Tables

The repository uses `app_` table prefixes, so Phase 8.5 adds:

- `app_chat_sessions`
- `app_chat_messages`
- `app_chat_tool_calls`
- `app_user_memories`

Migration:

- `supabase/migrations/0004_chat_history_memory.sql`

The runtime schema in `src/spectra/db.py` also creates these tables for fresh installs and backward-compatible startup migration.

## API Endpoints

Updated:

- `POST /api/chat`

New:

- `GET /api/chat/sessions`
- `GET /api/chat/sessions/{session_id}/messages`
- `POST /api/chat/sessions/{session_id}/archive`
- `DELETE /api/chat/sessions/{session_id}`
- `GET /api/chat/memories`
- `DELETE /api/chat/memories/{memory_id}`

All endpoints require an authenticated Spectra session and scope reads/writes by backend-derived `user_id`.

## Memory Rules

- Long-term memory writes require confirmation through `remember_user_preference`.
- Memory deletion through chat requires confirmation through `forget_user_memory`.
- The LLM cannot pass `user_id` to memory tools.
- Memory does not replace category rule tables, budget tables, goals, transactions, or financial-health services.
- Category learning remains handled by the existing confirmed category-rule flow.
- Current financial questions must call tools.

## Redaction Rules

Before persistence, Phase 8.5 redacts:

- Full account numbers.
- Bearer tokens.
- OpenAI-style API keys.
- Long numeric identifiers.
- Reference-like long identifiers.
- Raw stack traces.
- Sensitive metadata keys such as token, cookie, password, API key, and account number.

Amounts, merchant names, categories, and dates may be stored when needed for chat continuity.

## Example Flows

Continue previous goal:

1. User asks how to save 20 million VND in 6 months.
2. Assistant plans the goal and stores `last_goal_plan` in session memory.
3. User says `Tao muc tieu do di`.
4. Assistant uses session memory and creates a pending `create_savings_goal` confirmation.

Choose candidate transaction:

1. User asks to change Grab to transportation.
2. Assistant lists matching transactions and stores `last_transaction_candidates`.
3. User says `Cai thu 2`.
4. Assistant resolves candidate #2 and asks confirmation.

Apply last budget plan:

1. User asks how to split this month's budget.
2. Assistant recommends a plan and stores `last_budget_plan`.
3. User says `Ap dung ke hoach do di`.
4. Assistant asks confirmation for `upsert_budget_plan`.

Long-term preference:

1. User says `Lan sau tra loi ngan gon hon nhe`.
2. Assistant asks whether to remember the preference.
3. User confirms.
4. Assistant saves the safe preference after that explicit confirmation.

Current financial data:

- For questions like current spending, budget status, balances, anomalies, forecasts, goals, or financial health, the assistant must call current tools and not answer from stale memory.

## Manual Tests

1. `Toi muon tiet kiem 20 trieu trong 6 thang thi lam sao?`
2. `Tao muc tieu do di.`
3. `Doi giao dich Grab sang Di chuyen.`
4. `Cai thu 2.`
5. `Lan sau tra loi ngan gon hon nhe.`
6. `Ban nho gi ve toi?`
7. `Quen viec toi thich tra loi ngan gon di.`
8. `Thang nay toi tieu bao nhieu?`

Expected for question 8: the assistant must call current finance tools, not stale memory.

## Tests

Added:

- `tests/chatbot/test_memory_service.py`
- `tests/chatbot/test_context_builder.py`
- `tests/chatbot/test_phase8_5_memory_flows.py`

Updated:

- `tests/chatbot/test_chat_api.py`
- `tests/chatbot/test_tool_registry.py`

Verified:

- `uv run pytest -q`
- `npm run build`

Known lint state:

- `npm run lint` still fails on pre-existing unrelated frontend lint issues outside the chat panel.

## Known Limitations

- Pending confirmations remain in process memory and can disappear after restart.
- Conversation summarization uses the simple Phase 8.5 approach: last 12 messages, not generated summaries.
- Tool-call persistence stores structured traces and status, not full raw tool results.
- Memory export is effectively covered by `GET /api/chat/memories`; there is no dedicated download format yet.
- Memory deletion API deletes directly for authenticated users, while chat-initiated deletion requires confirmation.

## Phase 9 Recommendations

1. Persist pending confirmations and write audit records in database tables.
2. Add a dedicated chat history UI with session list and transcript loading.
3. Add generated safe conversation summaries for long sessions.
4. Add memory export/download endpoint.
5. Add latency metrics and richer tool-call result summaries.
6. Add frontend tests for session continuation and confirmation UI.
