"""Permission scope policy for chatbot tools.

Every registered tool declares a ``required_scope``. This module turns that
declaration into a real, fail-closed authorization check: a tool only runs if
the caller's granted scopes include the tool's required scope.

Currently every authenticated demo user owns their own finance data, so they
are granted the full set of standard scopes. To restrict a user/role later,
change :func:`resolve_granted_scopes` — that is the single policy hook.
"""

from __future__ import annotations

# Scopes granted to any authenticated user. This set is intentionally explicit
# (not derived from the registry) so a newly added tool with an unlisted scope
# is denied by default — fail closed.
DEFAULT_AUTHENTICATED_SCOPES: frozenset[str] = frozenset(
    {
        "account.read_basic",
        "analytics.read",
        "transactions.read_detail",
        "categories.read",
        "category.update",
        "rules.read",
        "rules.write",
        "memory.read",
        "memory.write",
        "anomaly.read",
        "forecast.read",
        "financial_health.read",
        "goals.read",
        "goals.write",
        "budget.read",
        "budget.write",
    }
)


def resolve_granted_scopes(user_id: str | None) -> frozenset[str]:
    """Return the set of permission scopes granted to ``user_id``.

    Policy hook: an empty/anonymous user gets nothing; an authenticated user
    gets the standard owner scope set. Tighten here to add roles or per-user
    grants without touching the guard or the tool registry.
    """
    if not str(user_id or "").strip():
        return frozenset()
    return DEFAULT_AUTHENTICATED_SCOPES
