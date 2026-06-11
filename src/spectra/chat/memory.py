"""Safe user and session memory helpers for the chatbot."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from spectra.chat.history import get_recent_messages
from spectra.chat.redaction import redact_payload

MEMORY_TYPES = {
    "preference",
    "conversation_summary",
    "last_goal_plan",
    "last_budget_plan",
    "last_transaction_candidates",
    "category_preference",
    "safety_preference",
    "ui_preference",
}

LONG_TERM_MEMORY_TYPES = {"preference", "category_preference", "safety_preference", "ui_preference"}
SESSION_MEMORY_TYPES = {"conversation_summary", "last_goal_plan", "last_budget_plan", "last_transaction_candidates"}

_SENSITIVE_KEY_RE = re.compile(
    r"(password|token|secret|api[_-]?key|openai|cookie|session|account[_-]?number|reference[_-]?number|auth)",
    re.IGNORECASE,
)
_LONG_NUMERIC_RE = re.compile(r"\b\d{10,19}\b")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return f"mem_{uuid4().hex}"


def _get_db():
    from spectra.web import server

    return server._get_db()


def _row_memory(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row[0]),
        "user_id": str(row[1]),
        "memory_type": str(row[2]),
        "key": str(row[3]),
        "value_json": row[4] if isinstance(row[4], dict) else {},
        "source": str(row[5] or "chat"),
        "confidence": float(row[6] or 0),
        "status": str(row[7] or "active"),
        "created_at": str(row[8] or ""),
        "updated_at": str(row[9] or ""),
        "expires_at": str(row[10] or "") if row[10] is not None else None,
    }


def get_user_memories(
    user_id: str,
    memory_types: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    requested = [item for item in (memory_types or []) if item in MEMORY_TYPES]
    bounded = max(1, min(int(limit or 50), 100))
    if requested:
        placeholders = ", ".join(["?"] * len(requested))
        sql = f"""
            SELECT id, user_id, memory_type, key, value_json, source, confidence, status, created_at, updated_at, expires_at
            FROM app_user_memories
            WHERE user_id = ? AND status = 'active' AND memory_type IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT ?
        """
        params: tuple[Any, ...] = (str(user_id), *requested, bounded)
    else:
        sql = """
            SELECT id, user_id, memory_type, key, value_json, source, confidence, status, created_at, updated_at, expires_at
            FROM app_user_memories
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT ?
        """
        params = (str(user_id), bounded)
    with _get_db() as db:
        rows = db._conn.execute(sql, params).fetchall()
    return [item for item in [_row_memory(row) for row in rows] if item]


def upsert_user_memory(
    user_id: str,
    memory_type: str,
    key: str,
    value: dict[str, Any],
    source: str = "chat",
    confidence: float = 1.0,
    expires_at: str | None = None,
) -> dict[str, Any]:
    user_id = str(user_id or "").strip()
    memory_type = str(memory_type or "").strip()
    key = str(key or "").strip()[:160]
    if not user_id:
        raise ValueError("user_id is required")
    if memory_type not in MEMORY_TYPES:
        raise ValueError("unsupported memory_type")
    if not key:
        raise ValueError("memory key is required")
    if has_sensitive_memory_payload({"key": key, "value": value}):
        raise ValueError("memory payload contains sensitive data")

    memory_id = _new_id()
    safe_value = redact_payload(value or {})
    now = _now_iso()
    with _get_db() as db:
        row = db._conn.execute(
            """
            INSERT INTO app_user_memories (
                id, user_id, memory_type, key, value_json, source, confidence, status, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            ON CONFLICT (user_id, memory_type, key) DO UPDATE SET
                value_json = EXCLUDED.value_json,
                source = EXCLUDED.source,
                confidence = EXCLUDED.confidence,
                status = 'active',
                updated_at = EXCLUDED.updated_at,
                expires_at = EXCLUDED.expires_at
            RETURNING id, user_id, memory_type, key, value_json, source, confidence, status, created_at, updated_at, expires_at
            """,
            (
                memory_id,
                user_id,
                memory_type,
                key,
                safe_value,
                str(source or "chat")[:80],
                max(0.0, min(float(confidence or 1.0), 1.0)),
                now,
                now,
                expires_at,
            ),
        ).fetchone()
        db._conn.commit()
    return _row_memory(row) or {"id": memory_id, "user_id": user_id, "memory_type": memory_type, "key": key}


def delete_user_memory(user_id: str, memory_id: str) -> dict[str, Any]:
    with _get_db() as db:
        row = db._conn.execute(
            """
            UPDATE app_user_memories
            SET status = 'deleted', updated_at = ?
            WHERE user_id = ? AND id = ?
            RETURNING id, user_id, memory_type, key, value_json, source, confidence, status, created_at, updated_at, expires_at
            """,
            (_now_iso(), str(user_id), str(memory_id)),
        ).fetchone()
        db._conn.commit()
    if not row:
        raise KeyError("memory not found")
    return _row_memory(row) or {}


def delete_user_memory_by_key(user_id: str, memory_type: str, key: str) -> dict[str, Any]:
    with _get_db() as db:
        row = db._conn.execute(
            """
            UPDATE app_user_memories
            SET status = 'deleted', updated_at = ?
            WHERE user_id = ? AND memory_type = ? AND key = ?
            RETURNING id, user_id, memory_type, key, value_json, source, confidence, status, created_at, updated_at, expires_at
            """,
            (_now_iso(), str(user_id), str(memory_type), str(key)),
        ).fetchone()
        db._conn.commit()
    if not row:
        raise KeyError("memory not found")
    return _row_memory(row) or {}


def save_session_state(user_id: str, session_id: str | None, memory_type: str, value: dict[str, Any]) -> dict[str, Any] | None:
    if not session_id or memory_type not in SESSION_MEMORY_TYPES:
        return None
    return upsert_user_memory(
        user_id=user_id,
        memory_type=memory_type,
        key=str(session_id),
        value=value,
        source="chat_session",
        confidence=1.0,
    )


def get_session_state(user_id: str, session_id: str | None, memory_type: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    matches = get_user_memories(user_id, memory_types=[memory_type], limit=20)
    for item in matches:
        if item.get("key") == str(session_id):
            value = item.get("value_json")
            return value if isinstance(value, dict) else None
    return None


def build_memory_context(user_id: str, session_id: str, recent_message_limit: int = 12) -> dict[str, Any]:
    recent_messages = get_recent_messages(session_id, user_id, limit=recent_message_limit)
    memories = get_user_memories(
        user_id,
        memory_types=["preference", "safety_preference", "ui_preference", "category_preference"],
        limit=30,
    )
    return {
        "recent_messages": recent_messages,
        "safe_user_memories": [
            {
                "id": item.get("id"),
                "memory_type": item.get("memory_type"),
                "key": item.get("key"),
                "value": item.get("value_json"),
            }
            for item in memories
        ],
        "session_state": {
            "last_goal_plan": get_session_state(user_id, session_id, "last_goal_plan"),
            "last_budget_plan": get_session_state(user_id, session_id, "last_budget_plan"),
            "last_transaction_candidates": get_session_state(user_id, session_id, "last_transaction_candidates"),
        },
    }


def extract_memory_candidates(
    user_message: str,
    assistant_message: str,
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return safe memory candidates; callers still need explicit confirmation."""
    normalized = _fold(user_message)
    candidates: list[dict[str, Any]] = []
    if any(token in normalized for token in ["tra loi ngan gon", "ngan gon hon", "shorter answer"]):
        candidates.append(
            {
                "memory_type": "preference",
                "key": "response_style",
                "value": {"preference": "shorter_answers"},
                "reason": "User asked for shorter future responses.",
                "requires_confirmation": True,
            }
        )
    if any(token in normalized for token in ["tra loi bang tieng viet", "vietnamese"]):
        candidates.append(
            {
                "memory_type": "preference",
                "key": "language",
                "value": {"language": "vi"},
                "reason": "User prefers Vietnamese responses.",
                "requires_confirmation": True,
            }
        )
    return [candidate for candidate in candidates if not has_sensitive_memory_payload(candidate)]


def has_sensitive_memory_payload(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                return True
            if has_sensitive_memory_payload(value):
                return True
        return False
    if isinstance(payload, list):
        return any(has_sensitive_memory_payload(item) for item in payload)
    if isinstance(payload, str):
        if _SENSITIVE_KEY_RE.search(payload):
            return True
        if _LONG_NUMERIC_RE.search(payload):
            return True
    return False


def _fold(value: str) -> str:
    value = str(value or "").replace("đ", "d").replace("Đ", "D")
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.lower().split())
