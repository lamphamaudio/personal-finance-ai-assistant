from fastapi.testclient import TestClient

from spectra.chat import history, memory
from spectra.chat.models import ChatResponse
from spectra.chat.supervisor import MissingOpenAIKeyError
from spectra.web import server


class _FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self):
        self.sessions = {}
        self.messages = []
        self.committed = False

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).lower().split())
        if normalized.startswith("select id, user_id, title") and "from app_chat_sessions" in normalized:
            session = self.sessions.get(params[0])
            if session and session[1] == params[1] and session[3] != "deleted":
                return _FakeResult(session)
            return _FakeResult()
        if normalized.startswith("select user_id from app_chat_sessions"):
            session = self.sessions.get(params[0])
            return _FakeResult((session[1],) if session else None)
        if "insert into app_chat_sessions" in normalized:
            row = (params[0], params[1], params[2], "active", params[3], params[4], None, params[5])
            self.sessions[params[0]] = row
            return _FakeResult(row)
        if "insert into app_chat_messages" in normalized:
            row = (params[0], params[1], params[2], params[3], params[4], params[5], params[6], params[7])
            self.messages.append(row)
            return _FakeResult(row)
        if "from app_chat_messages" in normalized:
            rows = [row for row in self.messages if row[1] == params[0] and row[2] == params[1]]
            return _FakeResult(rows=list(reversed(rows[-int(params[2]) :])))
        if "from app_user_memories" in normalized:
            return _FakeResult(rows=[])
        if normalized.startswith("update app_chat_sessions"):
            return _FakeResult()
        return _FakeResult()

    def commit(self):
        self.committed = True


class _FakeDb:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def _patch_chat_db(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(history, "_get_db", lambda: _FakeDb(conn))
    monkeypatch.setattr(memory, "_get_db", lambda: _FakeDb(conn))
    return conn


def test_chat_returns_401_when_unauthenticated():
    client = TestClient(server.app)

    response = client.post("/api/chat", json={"message": "Tháng này tôi tiêu nhiều nhất vào đâu?"})

    assert response.status_code == 401


def test_chat_handles_missing_openai_key_gracefully(monkeypatch):
    _patch_chat_db(monkeypatch)

    class FakeSupervisor:
        def __init__(self, request, user_id, **kwargs):
            pass

        async def respond(self, chat_request):
            raise MissingOpenAIKeyError("missing")

    monkeypatch.setattr(server, "_read_session_user_id", lambda request: "user-1")
    monkeypatch.setattr(server, "ChatSupervisor", FakeSupervisor)
    client = TestClient(server.app)

    response = client.post("/api/chat", json={"message": "Tóm tắt chi tiêu giúp tôi"})

    assert response.status_code == 503
    assert response.json()["error"] == "OpenAI is not configured"


def test_chat_creates_session_and_persists_messages(monkeypatch):
    conn = _patch_chat_db(monkeypatch)

    class FakeSupervisor:
        def __init__(self, request, user_id, **kwargs):
            assert kwargs["session_id"].startswith("chat_")

        async def respond(self, chat_request):
            return ChatResponse(answer="Xin chao", intent="GENERAL_FINANCE_ADVICE")

    monkeypatch.setattr(server, "_read_session_user_id", lambda request: "user-1")
    monkeypatch.setattr(server, "ChatSupervisor", FakeSupervisor)
    client = TestClient(server.app)

    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"].startswith("chat_")
    assert payload["message_id"].startswith("msg_")
    assert [row[3] for row in conn.messages] == ["user", "assistant"]
