"""In-memory pending confirmation store for chatbot write actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4


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
        return action

    def get(self, confirmation_id: str) -> PendingAction | None:
        with self._lock:
            action = self._actions.get(str(confirmation_id or ""))
            if action and action.status == "pending" and action.expires_at <= datetime.now(UTC):
                action.status = "expired"
            return action

    def cancel(self, confirmation_id: str, *, user_id: str) -> tuple[bool, str]:
        with self._lock:
            action = self._actions.get(str(confirmation_id or ""))
            if not action:
                return False, "Confirmation was not found."
            if action.user_id != str(user_id):
                return False, "Confirmation does not belong to this user."
            if action.status != "pending":
                return False, f"Confirmation is already {action.status}."
            action.status = "cancelled"
            return True, "Confirmation cancelled."

    def mark_confirmed(self, confirmation_id: str) -> None:
        with self._lock:
            action = self._actions.get(str(confirmation_id or ""))
            if action:
                action.status = "confirmed"

    def clear(self) -> None:
        with self._lock:
            self._actions.clear()


pending_actions = PendingActionStore()
