# Chatbot Phase 3 Write Confirmation MVP

## What Phase 3 Adds

Phase 3 adds controlled write capability for transaction category correction and category memory learning.

Implemented:

- In-memory pending confirmation store with 10 minute TTL
- Confirmation support on `POST /api/chat`
- Registered write tools gated by confirmation
- Category correction flow for a single matching transaction
- Ambiguous transaction response with up to 5 candidate rows
- Memory learning flow for category rules
- Read tools for category rules, rule testing, and learning summary
- Structured audit logging for confirmed write tool executions
- Tests for confirmation and write-tool safety

Not implemented:

- Database-backed pending actions
- Database audit log table
- Frontend chat confirmation UI
- Bulk category update through chat
- Learning reapply through chat
- Budget updates through chat
- Reset DB/admin tools
- Streaming chat

## New Tools

| Tool | Read/Write | Confirmation | Purpose |
|---|---:|---:|---|
| `update_transaction_category` | Write | Required | Update one authenticated user's transaction category. |
| `create_category_rule` | Write | Required | Create a future category memory rule. |
| `test_category_rule` | Read | No | Preview whether a proposed rule matches historical rows. |
| `get_category_rules` | Read | No | Return active category rules. |
| `get_learning_summary` | Read | No | Return recent learning summary with bounded events. |

Destructive/admin tools are not registered. `reset_db` and `learning_reapply` are intentionally unavailable.

## Confirmation Flow

Normal messages and confirmations both use `POST /api/chat`.

Confirmation request shape:

```json
{
  "message": "Dong y",
  "session_id": "optional",
  "scope": "cycle",
  "debug": false,
  "confirmation_id": "confirm_abc123",
  "confirm": true
}
```

If `confirmation_id` and `confirm=true` are present, the supervisor:

1. Loads the pending action.
2. Checks that it belongs to the authenticated user.
3. Checks that it is still pending and not expired.
4. Executes the stored tool through `ToolExecutor`.
5. Marks the pending action as confirmed.
6. Logs a structured audit event for write tools.

If `confirm=false`, the pending action is cancelled and never executed.

## Category Correction

Supported MVP flow:

1. User asks to change one transaction category.
2. Chatbot searches transactions by merchant text.
3. If one match is found, chatbot creates a pending `update_transaction_category` action and asks for confirmation.
4. If multiple matches are found, chatbot shows up to 5 candidates and asks the user to choose.
5. The transaction is updated only after confirmation.
6. After a successful update, chatbot asks whether to remember the rule for future transactions.

Bulk category changes are not executed in Phase 3.

## Memory Learning

The chatbot can create a category rule only after explicit confirmation.

Supported examples:

- After correcting a transaction, user says they want to remember it.
- User directly says a future rule such as `Lan sau thay Highlands thi xep vao Food`.

The chatbot creates a pending `create_category_rule` action and asks for final confirmation. It never creates a rule automatically after a single transaction update.

## Safety Rules

- LLM cannot call arbitrary endpoints.
- All tools are allowlisted in `src/spectra/chat/tools.py`.
- Write tools require a matching pending confirmation.
- Pending confirmations are bound to `user_id`.
- Expired, cancelled, confirmed, unknown, or cross-user confirmations are rejected.
- Candidate transaction output is bounded to 5 rows.
- Account/reference redaction still applies to tool output.
- Confirmed write tools are logged through structured audit logging.
- OpenAI API keys and sensitive raw financial data are not logged.

## Manual Test Cases

### Single Transaction Correction

Request:

```json
{"message": "doi giao dich Highlands sang Food"}
```

Expected:

- No immediate write.
- Chatbot asks for confirmation and returns a `confirmation_id`.

Confirm:

```json
{"message": "Dong y", "confirmation_id": "confirm_...", "confirm": true}
```

Expected:

- Transaction category is updated.
- Chatbot asks whether to remember a future rule.

### Multiple Matching Transactions

Request:

```json
{"message": "doi giao dich Grab sang Transport"}
```

Expected:

- Chatbot shows up to 5 matching candidates.
- No write is executed.

### Remember Rule

Request:

```json
{"message": "Lan sau thay Highlands thi xep vao Food"}
```

Expected:

- Chatbot asks for confirmation.
- Rule is created only after confirmation.

### Unsafe Action

Request:

```json
{"message": "xoa het du lieu di"}
```

Expected:

- Chatbot refuses or says unsupported.
- Reset DB is not called.

## Known Limitations

- Pending confirmations are process-local memory; they disappear on restart and are not shared across server replicas.
- The category correction parser is intentionally simple for the MVP.
- If multiple transactions match, the current implementation asks the user to choose but does not yet process a numbered follow-up selection.
- Audit logging is structured application logging only, not a database audit table.
- Rule and learning endpoints still have broader auth hardening work outside this chatbot tool layer.

## Phase 4 Recommendations

1. Persist pending actions and audit logs in database tables.
2. Add frontend confirmation controls.
3. Add deterministic follow-up handling for numbered candidate selection.
4. Add consent records for sensitive read tools.
5. Harden settings/rules/learning endpoints with explicit session checks.
6. Add safe multi-step bulk category correction only if product scope requires it.
