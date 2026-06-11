from fastapi.testclient import TestClient

from spectra.web import server


def test_chat_feedback_requires_authentication():
    client = TestClient(server.app)

    response = client.post("/api/chat/feedback", json={"rating": "up"})

    assert response.status_code == 401


def test_chat_feedback_validates_rating(monkeypatch):
    monkeypatch.setattr(server, "_read_session_user_id", lambda request: "user-1")
    client = TestClient(server.app)

    response = client.post("/api/chat/feedback", json={"rating": "maybe"})

    assert response.status_code == 400


def test_chat_feedback_rejects_huge_comment(monkeypatch):
    monkeypatch.setattr(server, "_read_session_user_id", lambda request: "user-1")
    client = TestClient(server.app)

    response = client.post("/api/chat/feedback", json={"rating": "down", "comment": "x" * 1001})

    assert response.status_code == 400


def test_chat_feedback_persists_minimal_fields(monkeypatch):
    captured = {}

    class FakeConn:
        def execute(self, sql, params):
            captured["params"] = params
            return self

        def fetchone(self):
            return (123,)

        def commit(self):
            captured["committed"] = True

    class FakeDb:
        def __init__(self):
            self._conn = FakeConn()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    monkeypatch.setattr(server, "_read_session_user_id", lambda request: "user-1")
    monkeypatch.setattr(server, "_get_db", lambda: FakeDb())
    client = TestClient(server.app)

    response = client.post(
        "/api/chat/feedback",
        json={"rating": "up", "comment": "helpful", "session_id": "s1", "message_id": "m1", "intent": "TEST"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["params"] == ("user-1", "s1", "m1", "up", "helpful", "TEST")
    assert captured["committed"] is True
