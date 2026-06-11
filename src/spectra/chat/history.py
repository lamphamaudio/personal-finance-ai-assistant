"""User-scoped chat session, message, and tool-call persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from spectra.chat.redaction import redact_payload, redact_text


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _get_db():
    from spectra.web import server

    return server._get_db()


def _row_session(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row[0]),
        "user_id": str(row[1]),
        "title": str(row[2] or ""),
        "status": str(row[3] or "active"),
        "created_at": str(row[4] or ""),
        "updated_at": str(row[5] or ""),
        "last_message_at": str(row[6] or "") if row[6] is not None else None,
        "metadata_json": row[7] if isinstance(row[7], dict) else {},
    }


def _row_message(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row[0]),
        "session_id": str(row[1]),
        "user_id": str(row[2]),
        "role": str(row[3]),
        "content": str(row[4] or ""),
        "intent": str(row[5] or "") or None,
        "created_at": str(row[6] or ""),
        "metadata_json": row[7] if isinstance(row[7], dict) else {},
    }


def _row_tool_call(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row[0]),
        "session_id": str(row[1]),
        "message_id": str(row[2] or "") or None,
        "user_id": str(row[3]),
        "tool_name": str(row[4]),
        "tool_arguments_json": row[5] if isinstance(row[5], dict) else {},
        "tool_result_summary_json": row[6] if isinstance(row[6], dict) else {},
        "status": str(row[7]),
        "latency_ms": int(row[8]) if row[8] is not None else None,
        "created_at": str(row[9] or ""),
        "error_message": str(row[10] or "") or None,
    }


def get_or_create_chat_session(user_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Return a user-owned chat session, creating one when needed."""
    user_id = str(user_id or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    requested_id = str(session_id or "").strip()
    with _get_db() as db:
        if requested_id:
            row = db._conn.execute(
                """
                SELECT id, user_id, title, status, created_at, updated_at, last_message_at, metadata_json
                FROM app_chat_sessions
                WHERE id = ? AND user_id = ? AND status != 'deleted'
                """,
                (requested_id, user_id),
            ).fetchone()
            if row:
                return _row_session(row) or {}
            existing = db._conn.execute("SELECT user_id FROM app_chat_sessions WHERE id = ?", (requested_id,)).fetchone()
            if existing and str(existing[0]) != user_id:
                requested_id = ""

        new_id = requested_id if requested_id.startswith("chat_") and len(requested_id) <= 120 else _new_id("chat")
        row = db._conn.execute(
            """
            INSERT INTO app_chat_sessions (id, user_id, title, status, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, 'active', ?, ?, ?)
            RETURNING id, user_id, title, status, created_at, updated_at, last_message_at, metadata_json
            """,
            (new_id, user_id, "", _now_iso(), _now_iso(), {}),
        ).fetchone()
        db._conn.commit()
        return _row_session(row) or {"id": new_id, "user_id": user_id, "status": "active"}


def save_chat_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = str(role or "").strip().lower()
    if role not in {"user", "assistant", "system", "tool"}:
        raise ValueError("invalid chat message role")
    message_id = _new_id("msg")
    redacted_content = redact_text(str(content or ""))[:8000]
    redacted_metadata = redact_payload(metadata or {})
    now = _now_iso()
    with _get_db() as db:
        row = db._conn.execute(
            """
            INSERT INTO app_chat_messages (id, session_id, user_id, role, content, intent, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, session_id, user_id, role, content, intent, created_at, metadata_json
            """,
            (message_id, str(session_id), str(user_id), role, redacted_content, intent, now, redacted_metadata),
        ).fetchone()
        title = redacted_content[:80] if role == "user" else ""
        db._conn.execute(
            """
            UPDATE app_chat_sessions
            SET updated_at = ?, last_message_at = ?,
                title = CASE WHEN COALESCE(title, '') = '' AND ? != '' THEN ? ELSE title END
            WHERE id = ? AND user_id = ?
            """,
            (now, now, title, title, str(session_id), str(user_id)),
        )
        db._conn.commit()
    return _row_message(row) or {"id": message_id, "session_id": session_id, "user_id": user_id, "role": role}


def get_recent_messages(session_id: str, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit or 20), 50))
    with _get_db() as db:
        rows = db._conn.execute(
            """
            SELECT id, session_id, user_id, role, content, intent, created_at, metadata_json
            FROM app_chat_messages
            WHERE session_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(session_id), str(user_id), bounded),
        ).fetchall()
    return [item for item in reversed([_row_message(row) for row in rows]) if item]


def save_tool_call(
    session_id: str,
    message_id: str | None,
    user_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result_summary: dict[str, Any],
    status: str,
    latency_ms: int | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    tool_call_id = _new_id("tool")
    safe_args = redact_payload(arguments or {})
    safe_summary = redact_payload(result_summary or {})
    safe_error = redact_text(str(error_message or ""))[:1000] or None
    with _get_db() as db:
        row = db._conn.execute(
            """
            INSERT INTO app_chat_tool_calls (
                id, session_id, message_id, user_id, tool_name, tool_arguments_json,
                tool_result_summary_json, status, latency_ms, created_at, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, session_id, message_id, user_id, tool_name, tool_arguments_json,
                tool_result_summary_json, status, latency_ms, created_at, error_message
            """,
            (
                tool_call_id,
                str(session_id),
                str(message_id or ""),
                str(user_id),
                str(tool_name),
                safe_args,
                safe_summary,
                str(status),
                latency_ms,
                _now_iso(),
                safe_error,
            ),
        ).fetchone()
        db._conn.commit()
    return _row_tool_call(row) or {"id": tool_call_id, "session_id": session_id, "tool_name": tool_name}


def list_chat_sessions(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit or 20), 100))
    with _get_db() as db:
        rows = db._conn.execute(
            """
            SELECT id, user_id, title, status, created_at, updated_at, last_message_at, metadata_json
            FROM app_chat_sessions
            WHERE user_id = ? AND status != 'deleted'
            ORDER BY COALESCE(last_message_at, created_at) DESC
            LIMIT ?
            """,
            (str(user_id), bounded),
        ).fetchall()
    return [item for item in [_row_session(row) for row in rows] if item]


def archive_chat_session(user_id: str, session_id: str) -> dict[str, Any]:
    return _update_session_status(user_id, session_id, "archived")


def delete_chat_session(user_id: str, session_id: str) -> dict[str, Any]:
    return _update_session_status(user_id, session_id, "deleted")


def _update_session_status(user_id: str, session_id: str, status: str) -> dict[str, Any]:
    with _get_db() as db:
        row = db._conn.execute(
            """
            UPDATE app_chat_sessions
            SET status = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            RETURNING id, user_id, title, status, created_at, updated_at, last_message_at, metadata_json
            """,
            (status, _now_iso(), str(session_id), str(user_id)),
        ).fetchone()
        db._conn.commit()
    if not row:
        raise KeyError("chat session not found")
    return _row_session(row) or {}
