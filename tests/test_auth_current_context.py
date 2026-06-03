from fastapi.testclient import TestClient

from spectra.web import server


def test_current_context_returns_401_when_unauthenticated():
    client = TestClient(server.app)

    response = client.get("/api/auth/current-context")

    assert response.status_code == 401


def test_current_context_returns_spectra_and_bank_user(monkeypatch):
    monkeypatch.setattr(server, "_read_session_user_id", lambda request: "user-1")
    monkeypatch.setattr(
        server,
        "_fetch_demo_user",
        lambda user_id: {
            "user_id": user_id,
            "persona_type": "Student",
            "account_number": "1234567890",
            "bank_name": "TPBank",
            "current_balance": 1000000.0,
        },
    )
    client = TestClient(server.app)

    response = client.get("/api/auth/current-context")

    assert response.status_code == 200
    data = response.json()
    assert data["spectra"]["user_id"] == "user-1"
    assert data["bank_simulator"]["bank_name"] == "TPBank"
    assert data["bank_simulator"]["account_number_masked"] == "******7890"
    assert "account_number" not in data["bank_simulator"]
