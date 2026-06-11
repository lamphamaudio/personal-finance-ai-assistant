import pytest

from spectra import config
from spectra.chat.confirmation import pending_actions


@pytest.fixture(autouse=True)
def isolate_chatbot_side_effects(monkeypatch):
    monkeypatch.setenv("CHAT_FINALIZER_ENABLED", "false")
    monkeypatch.setattr(pending_actions, "_persist", lambda action: None)
    monkeypatch.setattr(pending_actions, "_load", lambda confirmation_id: None)
    monkeypatch.setattr(pending_actions, "_update_status", lambda confirmation_id, status: None)
    pending_actions.clear()
    config._SETTINGS_CACHE = None
    yield
    pending_actions.clear()
    config._SETTINGS_CACHE = None
