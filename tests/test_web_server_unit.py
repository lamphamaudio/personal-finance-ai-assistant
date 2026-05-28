from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from spectra.web.server import app


@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mock context manager
    db.__enter__.return_value = db
    db.__exit__.return_value = None
    return db

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_transactions_page(client):
    response = client.get("/transactions")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_upload_page(client):
    response = client.get("/upload")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_settings_page(client):
    response = client.get("/settings")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_subscriptions_page(client):
    response = client.get("/subscriptions")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_budget_page(client):
    response = client.get("/budget")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_trends_page(client):
    response = client.get("/trends")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

@patch("spectra.web.server._get_db")
def test_api_categories(mock_get_db_fn, client, mock_db):
    mock_get_db_fn.return_value = mock_db
    mock_db._conn.execute.return_value.fetchall.return_value = [("Food",), ("Rent",)]
    
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == {"categories": ["Food", "Nhà ở"]}

@patch("spectra.web.server._get_db")
def test_api_delete_category_rule(mock_get_db_fn, client, mock_db):
    mock_get_db_fn.return_value = mock_db
    mock_db.delete_category_rule.return_value = True
    
    response = client.delete("/api/settings/rules/123")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": 123}
    mock_db.delete_category_rule.assert_called_with(123)

@patch("spectra.web.server._get_db")
def test_api_delete_category_rule_not_found(mock_get_db_fn, client, mock_db):
    mock_get_db_fn.return_value = mock_db
    mock_db.delete_category_rule.return_value = False
    
    response = client.delete("/api/settings/rules/999")
    assert response.status_code == 404
    assert response.json() == {"error": "Rule not found"}

@patch("spectra.web.server._get_db")
def test_api_create_category_rule_validation(mock_get_db_fn, client, mock_db):
    # Test missing pattern
    response = client.post("/api/settings/rules", json={"category": "Food"})
    assert response.status_code == 400
    assert "pattern is required" in response.json()["error"]
    
    # Test missing category
    response = client.post("/api/settings/rules", json={"pattern": "test"})
    assert response.status_code == 400
    assert "category is required" in response.json()["error"]

