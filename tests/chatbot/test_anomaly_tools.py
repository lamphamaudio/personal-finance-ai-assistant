import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_get_anomalies_clamps_limit_and_ignores_user_id(monkeypatch):
    from spectra.chat import finance_tools

    captured = {}

    def fake_get_anomalies_for_chat(user_id, *, limit, scope):
        captured.update({"user_id": user_id, "limit": limit, "scope": scope})
        return {"anomalies": [], "summary": {"total": 0, "high": 0, "medium": 0, "low": 0}, "data_source": "test"}

    monkeypatch.setattr(finance_tools, "get_anomalies_for_chat", fake_get_anomalies_for_chat)
    executor = ToolExecutor(_request(), user_id="real-user")

    result = asyncio.run(executor.execute("get_anomalies", {"limit": 200, "scope": "90d", "user_id": "other-user"}))

    assert result.status == "success"
    assert captured == {"user_id": "real-user", "limit": 20, "scope": "90d"}


def test_get_anomalies_returns_safe_normalized_fields(monkeypatch):
    from spectra.chat import finance_tools

    def fake_get_anomalies_for_chat(user_id, *, limit, scope):
        return {
            "anomalies": [
                {
                    "id": "safe-id",
                    "date": "2026-06-02",
                    "merchant": "Highlands",
                    "amount": 650000,
                    "category": "Food",
                    "severity": "medium",
                    "reason": "Higher than usual",
                    "reference_number": "123456789012",
                }
            ],
            "summary": {"total": 1, "high": 0, "medium": 1, "low": 0},
            "data_source": "bank_simulator",
            "limitations": [],
        }

    monkeypatch.setattr(finance_tools, "get_anomalies_for_chat", fake_get_anomalies_for_chat)
    executor = ToolExecutor(_request(), user_id="real-user")

    result = asyncio.run(executor.execute("get_anomalies", {"limit": 10}))

    anomaly = result.data["anomalies"][0]
    assert set(anomaly) >= {"id", "date", "merchant", "amount", "category", "severity", "reason"}
    assert anomaly["reference_number"] == "********9012"


def test_explain_anomaly_is_read_only_and_user_bound(monkeypatch):
    from spectra.chat import finance_tools

    captured = {}

    def fake_explain(user_id, anomaly_id):
        captured.update({"user_id": user_id, "anomaly_id": anomaly_id})
        return {"found": True, "anomaly": {"id": anomaly_id}, "explanation": {"why_unusual": "test"}}

    monkeypatch.setattr(finance_tools, "explain_anomaly_for_chat", fake_explain)
    executor = ToolExecutor(_request(), user_id="real-user")

    result = asyncio.run(executor.execute("explain_anomaly", {"anomaly_id": "a-1", "user_id": "other-user"}))

    assert result.status == "success"
    assert captured == {"user_id": "real-user", "anomaly_id": "a-1"}
