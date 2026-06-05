import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from spectra.web import server


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/summary", None),
        ("GET", "/api/transactions", None),
        ("GET", "/api/budget", None),
        ("GET", "/api/trends", None),
        ("GET", "/api/subscriptions", None),
        ("GET", "/api/categories", None),
        ("GET", "/api/categories/options", None),
        ("GET", "/api/settings", None),
        ("GET", "/api/settings/rules", None),
        ("GET", "/api/settings/learning", None),
        ("POST", "/api/settings/learning/reapply", {}),
        ("POST", "/api/settings/reset-db", {"confirm": "RESET"}),
        ("POST", "/api/confirm", {"transactions": []}),
    ],
)
def test_sensitive_api_routes_require_authentication(method, path, json_body):
    client = TestClient(server.app)

    response = client.request(method, path, json=json_body)

    assert response.status_code == 401
    assert response.json()["error"] == "Not authenticated"


class _FakeResult:
    rowcount = 0

    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self):
        self.updated = []

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).lower().split())
        if normalized.startswith("select clean_name"):
            if tuple(params) == ("tx-other", "user-a"):
                return _FakeResult(row=None)
            return _FakeResult(row=("Other Merchant", "raw", "Khác"))
        if normalized.startswith("update app_tx_history"):
            self.updated.append(tuple(params))
            return _FakeResult(rowcount=1)
        return _FakeResult()

    def commit(self):
        return None


class _FakeDb:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def _request(body: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/transactions/tx-other",
            "headers": [(b"content-type", b"application/json")],
        },
        receive=receive,
    )


def test_update_transaction_is_scoped_to_authenticated_user(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(server, "_require_session_user_id", lambda request: "user-a")
    monkeypatch.setattr(server, "_get_db", lambda: _FakeDb(conn))

    response = asyncio.run(server.api_update_transaction("tx-other", _request(b'{"category":"Food"}')))

    assert response.status_code == 404
    assert conn.updated == []
