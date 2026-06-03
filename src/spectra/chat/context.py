"""Compact context builder for chatbot supervision."""

from __future__ import annotations

from typing import Any

from spectra.chat.memory import build_memory_context


def build_chat_context(user_id: str, session_id: str, current_message: str) -> dict[str, Any]:
    """Build bounded context for the supervisor without treating memory as financial truth."""
    memory_context = build_memory_context(user_id, session_id, recent_message_limit=12)
    session_state = memory_context.get("session_state") or {}
    return {
        "current_message": str(current_message or "")[:4000],
        "recent_messages": list(memory_context.get("recent_messages") or [])[-12:],
        "safe_user_memories": list(memory_context.get("safe_user_memories") or [])[:30],
        "pending_confirmations": [],
        "last_goal_plan": session_state.get("last_goal_plan"),
        "last_budget_plan": session_state.get("last_budget_plan"),
        "last_transaction_candidates": session_state.get("last_transaction_candidates"),
        "rules": [
            "Use recent chat only to resolve references.",
            "Call tools for current balances, spending, budgets, goals, anomalies, and forecasts.",
            "Do not treat old chat or memory as current financial truth.",
            "Do not store long-term memory without explicit confirmation.",
        ],
    }
