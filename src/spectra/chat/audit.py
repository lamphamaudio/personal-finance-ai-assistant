"""Structured audit logging for confirmed chatbot write tools."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

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
    safe_arguments = {key: value for key, value in arguments.items() if "key" not in key.lower()}
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
                "created_at": datetime.now(UTC).isoformat(),
                "error_message": error_message,
            },
            ensure_ascii=False,
            default=str,
        ),
    )
