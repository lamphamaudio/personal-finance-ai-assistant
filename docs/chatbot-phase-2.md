# Chatbot Phase 2 Read-Only MVP

## What Was Implemented

Phase 2 adds a read-only chatbot backend MVP for Personal Finance AI Assistant v3.

Implemented:

- `POST /api/chat`
- Chat request/response Pydantic models
- Read-only tool registry
- Read-only tool executor
- OpenAI Chat Completions supervisor with tool calling
- Basic account/reference redaction helpers
- Unit tests for registry, executor guardrails, redaction, and route auth/error behavior

Not implemented in Phase 2:

- Consent database or consent UI
- Write tools
- Transaction category updates through chat
- Category rule creation through chat
- Budget updates through chat
- Learning reapply through chat
- Financial health score
- Audit log table
- Chat persistence
- Streaming
- Frontend chat UI
- Admin/destructive tools

## New Files

| File | Purpose |
|---|---|
| `src/spectra/chat/__init__.py` | Chat package marker. |
| `src/spectra/chat/models.py` | Chat API and tool Pydantic models. |
| `src/spectra/chat/prompts.py` | Vietnamese supervisor system prompt. |
| `src/spectra/chat/tools.py` | Phase 2 read-only tool registry. |
| `src/spectra/chat/executor.py` | Backend-controlled tool executor. |
| `src/spectra/chat/supervisor.py` | OpenAI supervisor and tool-calling flow. |
| `src/spectra/chat/redaction.py` | Account/reference masking helpers. |
| `tests/chatbot/test_chat_api.py` | `/api/chat` auth and missing-key tests. |
| `tests/chatbot/test_tool_registry.py` | Registry tests. |
| `tests/chatbot/test_tool_executor.py` | Executor rejection and pagination tests. |
| `tests/chatbot/test_redaction.py` | Redaction tests. |

Modified:

- `src/spectra/web/server.py`: adds the thin `POST /api/chat` route.

## New Endpoint

`POST /api/chat`

Request:

```json
{
  "message": "Tháng này tôi tiêu nhiều nhất vào đâu?",
  "session_id": "optional-client-session-id",
  "scope": "cycle",
  "debug": false
}
```

Response:

```json
{
  "answer": "Tháng này bạn chi nhiều nhất vào...",
  "intent": "SPENDING_BREAKDOWN",
  "tool_calls": [
    {
      "tool_name": "get_account_summary",
      "arguments": {"scope": "cycle"},
      "status": "success",
      "error": null
    }
  ],
  "requires_confirmation": false,
  "suggested_actions": [],
  "debug": null
}
```

Behavior:

- Returns `401` if there is no authenticated Spectra session.
- Returns `503` if `OPENAI_API_KEY` is missing.
- Answers in Vietnamese by default.
- Does not expose write/admin/destructive tools.
- Does not provide personal financial facts without tool data.

## Registered Tools

Only these four tools are registered in Phase 2:

| Tool | Existing Source | Read/Write | Notes |
|---|---|---:|---|
| `get_current_user` | `_fetch_demo_user` in `src/spectra/web/server.py` | Read | Masks account number and does not expose balance. |
| `get_account_summary` | `GET /api/summary` handler logic | Read | Preferred aggregate analytics tool. |
| `get_transactions` | `GET /api/transactions` handler logic | Read | Defaults to `per_page=20`; chatbot max is `50`. |
| `get_category_options` | `GET /api/categories/options` handler logic | Read | Returns known categories for the authenticated user. |

## Environment Variables

Required:

```powershell
$env:OPENAI_API_KEY="..."
```

Optional:

```powershell
$env:OPENAI_MODEL="gpt-4o-mini"
```

`OPENAI_API_KEY` and `OPENAI_MODEL` are loaded through the existing `Settings` config in `src/spectra/config.py`. If no model is configured, the existing default is `gpt-4o-mini`.

## Manual Test

1. Set environment:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-4o-mini"
```

2. Start Spectra:

```powershell
uv run spectra --serve --port 8080
```

3. Log in through the UI so the browser has a valid `spectra_session` cookie.

4. Call:

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Tháng này tôi tiêu nhiều nhất vào đâu?",
  "scope": "cycle"
}
```

Expected result:

- The route checks the session.
- The supervisor chooses `get_account_summary`.
- The answer explains spending categories in Vietnamese, grounded in `/api/summary` data.

## Test Command

```powershell
pytest tests/chatbot
```

Full suite:

```powershell
pytest
```

## Limitations

- No chat persistence.
- No consent database or consent UI.
- No audit log table.
- No streaming response.
- No frontend chat UI.
- Unsupported intents such as anomaly explanation, balance forecast, category correction writes, and financial health score return a Phase 2 limitation message.
- Only one tool call is executed per chat request.
- Transaction detail access is bounded but still sensitive; Phase 3 should add consent and stronger redaction.

## Recommended Phase 3 Next Steps

1. Add consent tables and consent APIs for sensitive read and all write tools.
2. Add audit log tables for chat requests, tool calls, and tool outputs.
3. Add write-tool confirmation flow for category updates and budget changes.
4. Add financial health score service.
5. Add Spectra-native anomaly and forecast services.
6. Add frontend chat UI with confirmation prompts.
