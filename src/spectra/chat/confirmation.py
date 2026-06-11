"""Pending confirmation store for chatbot write actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

logger = logging.getLogger("spectra.chat.confirmation")


@dataclass
class PendingAction:
    confirmation_id: str
    user_id: str
    action_type: str
    tool_name: str
    tool_arguments: dict[str, Any]
    human_summary: str
    created_at: datetime
    expires_at: datetime
    status: str = "pending"


class PendingActionStore:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._actions: dict[str, PendingAction] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        user_id: str,
        action_type: str,
        tool_name: str,
        tool_arguments: dict[str, Any],
        human_summary: str,
    ) -> PendingAction:
        now = datetime.now(UTC)
        action = PendingAction(
            confirmation_id=f"confirm_{uuid4().hex[:12]}",
            user_id=str(user_id),
            action_type=action_type,
            tool_name=tool_name,
            tool_arguments=dict(tool_arguments),
            human_summary=human_summary,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            self._actions[action.confirmation_id] = action
        self._persist(action)
        return action

    def get(self, confirmation_id: str) -> PendingAction | None:
        key = str(confirmation_id or "")
        with self._lock:
            action = self._actions.get(key)
        if not action:
            action = self._load(key)
            if action:
                with self._lock:
                    self._actions[action.confirmation_id] = action
        with self._lock:
            if action and action.status == "pending" and action.expires_at <= datetime.now(UTC):
                action.status = "expired"
                self._update_status(action.confirmation_id, "expired")
            return action

    def cancel(self, confirmation_id: str, *, user_id: str) -> tuple[bool, str]:
        with self._lock:
            action = self._actions.get(str(confirmation_id or ""))
        if not action:
            action = self._load(str(confirmation_id or ""))
            if action:
                with self._lock:
                    self._actions[action.confirmation_id] = action
        with self._lock:
            if not action:
                return False, "Confirmation was not found."
            if action.user_id != str(user_id):
                return False, "Confirmation does not belong to this user."
            if action.status != "pending":
                return False, f"Confirmation is already {action.status}."
            action.status = "cancelled"
        self._update_status(str(confirmation_id or ""), "cancelled")
        return True, "Confirmation cancelled."

    def mark_confirmed(self, confirmation_id: str) -> None:
        with self._lock:
            action = self._actions.get(str(confirmation_id or ""))
            if action:
                action.status = "confirmed"
        self._update_status(str(confirmation_id or ""), "confirmed")

    def clear(self) -> None:
        with self._lock:
            self._actions.clear()

    def _persist(self, action: PendingAction) -> None:
        try:
            with _get_db() as db:
                db._conn.execute(
                    """
                    INSERT INTO app_chat_pending_confirmations (
                        id, user_id, action_type, tool_name, tool_arguments_json,
                        human_summary, status, created_at, expires_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        action.confirmation_id,
                        action.user_id,
                        action.action_type,
                        action.tool_name,
                        action.tool_arguments,
                        action.human_summary,
                        action.status,
                        action.created_at.isoformat(),
                        action.expires_at.isoformat(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                db._conn.commit()
        except Exception:
            logger.debug("Could not persist pending confirmation", exc_info=True)

    def _load(self, confirmation_id: str) -> PendingAction | None:
        if not confirmation_id:
            return None
        try:
            with _get_db() as db:
                row = db._conn.execute(
                    """
                    SELECT id, user_id, action_type, tool_name, tool_arguments_json,
                           human_summary, created_at, expires_at, status
                    FROM app_chat_pending_confirmations
                    WHERE id = ?
                    """,
                    (confirmation_id,),
                ).fetchone()
        except Exception:
            logger.debug("Could not load pending confirmation", exc_info=True)
            return None
        if not row:
            return None
        raw_args = row[4] if isinstance(row[4], dict) else {}
        return PendingAction(
            confirmation_id=str(row[0]),
            user_id=str(row[1]),
            action_type=str(row[2]),
            tool_name=str(row[3]),
            tool_arguments=dict(raw_args),
            human_summary=str(row[5] or ""),
            created_at=_parse_dt(row[6]),
            expires_at=_parse_dt(row[7]),
            status=str(row[8] or "pending"),
        )

    def _update_status(self, confirmation_id: str, status: str) -> None:
        if not confirmation_id:
            return
        try:
            with _get_db() as db:
                db._conn.execute(
                    """
                    UPDATE app_chat_pending_confirmations
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, datetime.now(UTC).isoformat(), confirmation_id),
                )
                db._conn.commit()
        except Exception:
            logger.debug("Could not update pending confirmation status", exc_info=True)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _get_db():
    from spectra.web import server

    return server._get_db()


pending_actions = PendingActionStore()
