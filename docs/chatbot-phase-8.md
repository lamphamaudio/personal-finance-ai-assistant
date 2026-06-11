# Chatbot Phase 8 Chat UI And Product Polish

## What Phase 8 Adds

Phase 8 makes the chatbot usable from the dashboard:

- Floating dashboard chat drawer
- Chat API client for `POST /api/chat`
- Assistant/user message rendering
- Prompt chips for demo questions
- Suggested action buttons
- Confirmation card with confirm/cancel actions
- Loading and error states
- Opt-in debug tool trace
- Feedback buttons and `POST /api/chat/feedback`
- Evaluation dataset in `docs/chatbot-evaluation.md`

No new finance capability is added in this phase.

## UI Structure

React components live under:

- `frontend/src/components/chat/ChatPanel.jsx`

The panel is mounted from the dashboard page. It opens from a floating `Tro ly` button and sends requests using the existing API client.

## API Contract

Normal message:

```json
{
  "message": "Tong quan tai chinh cua toi the nao?",
  "session_id": "chat_...",
  "scope": "cycle",
  "debug": false
}
```

Confirmation:

```json
{
  "message": "Xac nhan",
  "session_id": "chat_...",
  "confirmation_id": "confirm_abc",
  "confirm": true,
  "scope": "cycle",
  "debug": false
}
```

## Confirmation UI

When `requires_confirmation=true`, the UI renders a confirmation card using `confirmation.summary`.

Confirm sends:

- `confirmation_id`
- `confirm=true`

Cancel sends:

- `confirmation_id`
- `confirm=false`

The frontend never calls write tools or write APIs directly from chatbot interactions.

## Suggested Actions

The UI renders `suggested_actions` as buttons.

- `confirm` sends confirmation payload.
- `cancel` sends cancellation payload.
- `follow_up` sends the action label/message as a new chat message.

## Debug Mode

Debug mode is opt-in:

- URL query: `?debug_chat=1`
- Local storage: `spectra-chat-debug=1`

Debug shows:

- intent
- tool calls
- tool arguments
- tool status
- confirmation metadata

Normal users do not see tool traces.

## Feedback

`POST /api/chat/feedback` stores lightweight feedback:

```json
{
  "session_id": "chat_001",
  "message_id": "msg_001",
  "rating": "up",
  "comment": "",
  "intent": "BUDGET"
}
```

Rules:

- Requires authenticated user.
- Rating must be `up` or `down`.
- Comment is capped at 1000 characters.
- Sensitive raw payloads are not stored.

## Demo Script

1. Login as a demo user.
2. Open the dashboard.
3. Open the chat panel.
4. Ask: `Tong quan tai chinh cua toi the nao?`
5. Ask: `Co khoan nao bat thuong khong?`
6. Ask: `Cuoi thang toi con khoang bao nhieu?`
7. Ask: `Tai chinh cua toi co on khong?`
8. Ask: `Toi muon tiet kiem 20 trieu trong 6 thang thi lam sao?`
9. Ask: `Tao muc tieu do di.`
10. Click confirm.
11. Ask: `Toi nen chia ngan sach thang nay the nao?`
12. Ask: `Giam ngan sach mua sam xuong 2 trieu.`
13. Click cancel first.
14. Ask again and click confirm.
15. Ask: `Toi nen mua coin nao?`
16. Verify investment advice is refused.

## Known Limitations

- Chat history is kept in browser memory only.
- Feedback stores rating/comment but not full message transcripts.
- No frontend automated tests are configured yet.
- Debug trace does not include latency timing yet.

## Phase 9 Recommendations

1. Add persistent chat transcripts with redaction.
2. Add frontend component tests.
3. Add latency and tool duration metrics.
4. Add a dedicated chat page for long-running workflows.
5. Add evaluation runner that replays `docs/chatbot-evaluation.md`.
