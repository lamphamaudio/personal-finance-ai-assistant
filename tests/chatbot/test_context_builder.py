from spectra.chat import context


def test_context_builder_limits_recent_messages(monkeypatch):
    messages = [{"role": "user", "content": f"m{i}"} for i in range(20)]

    def fake_memory_context(user_id, session_id, recent_message_limit=12):
        return {
            "recent_messages": messages,
            "safe_user_memories": [],
            "session_state": {"last_goal_plan": {"name": "Goal"}},
        }

    monkeypatch.setattr(context, "build_memory_context", fake_memory_context)

    built = context.build_chat_context("user-1", "chat-1", "current")

    assert len(built["recent_messages"]) == 12
    assert built["last_goal_plan"] == {"name": "Goal"}
    assert "Call tools for current balances" in built["rules"][1]
