"""Structured audit logging for confirmed chatbot write tools."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from spectra.chat.redaction import redact_payload, redact_text

logger = logging.getLogger("spectra.chat.audit")


def log_write_tool_call(
    *,
    user_id: str,
    session_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    confirmation_id: str,
    error_message: str | None = None,
) -> None:
    safe_arguments = redact_payload({key: value for key, value in arguments.items() if "key" not in key.lower()})
    created_at = datetime.now(UTC).isoformat()
    try:
        with _get_db() as db:
            db._conn.execute(
                """
                INSERT INTO app_chat_audit_log (
                    id, user_id, session_id, tool_name, tool_arguments_json,
                    status, confirmation_id, error_message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"audit_{uuid4().hex}",
                    str(user_id or ""),
                    str(session_id or ""),
                    str(tool_name),
                    safe_arguments,
                    str(status),
                    str(confirmation_id or ""),
                    redact_text(str(error_message or ""))[:1000] or None,
                    created_at,
                ),
            )
            db._conn.commit()
    except Exception:
        logger.debug("Could not persist chat write audit log", exc_info=True)

    logger.info(
        "chat_write_tool_call %s",
        json.dumps(
            {
                "user_id": user_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_arguments_json": safe_arguments,
                "status": status,
                "confirmation_id": confirmation_id,
                "created_at": created_at,
                "error_message": error_message,
            },
            ensure_ascii=False,
            default=str,
        ),
    )


def _get_db():
    from spectra.web import server

    return server._get_db()
