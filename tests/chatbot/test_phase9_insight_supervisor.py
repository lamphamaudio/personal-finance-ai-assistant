import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest, ToolExecutionResult
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


async def _fake_execute(self, tool_name, arguments=None, **kwargs):
    data_by_tool = {
        "compare_period_spending": {
            "totals": {"period_a_spent": 2_000_000, "period_b_spent": 1_500_000, "spent_delta": 500_000},
            "category_deltas": [{"category": "Food", "delta": 300_000}],
        },
        "explain_budget_overrun": {
            "categories": [
                {
                    "category": "Food",
                    "actual_spend": 1_200_000,
                    "budget_limit": 1_000_000,
                    "top_drivers": [{"date": "2026-06-01", "merchant": "Restaurant", "amount": 900_000}],
                }
            ]
        },
        "simulate_purchase_impact": {
            "purchase": {"amount": 15_000_000},
            "impact": {"predicted_end_balance_after": 1_000_000},
            "recommendation": {"label": "risky", "reason": "test"},
        },
        "get_emergency_fund_status": {
            "months_target": 3,
            "monthly_essential_spend": 3_000_000,
            "estimated_months_covered": 2,
            "target_amount": 9_000_000,
            "gap_amount": 3_000_000,
            "status": "partial",
        },
        "get_debt_summary": {
            "summary": {"debt_like_payment_count": 1, "debt_like_paid_amount": 1_500_000},
            "items": [{"merchant": "Bank Loan", "paid_amount": 1_500_000}],
        },
        "get_recurring_transactions": {
            "summary": {"active_count": 1, "monthly_estimate": 250_000, "price_change_count": 0},
            "items": [{"merchant": "Netflix", "monthly_estimate": 250_000, "kind": "subscription"}],
        },
        "get_cashflow_calendar": {
            "current_balance": 5_000_000,
            "avg_daily_spending": 200_000,
            "risk_days": [],
            "upcoming_events": [],
        },
    }
    return ToolExecutionResult(tool_name=tool_name, status="success", data=data_by_tool.get(tool_name, {}))


def test_supervisor_routes_period_comparison(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Thang nay so voi thang truoc tang giam o dau?")))

    assert response.tool_calls[0].tool_name == "compare_period_spending"


def test_supervisor_routes_budget_overrun_explanation(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Tai sao toi vuot ngan sach an uong?")))

    assert response.tool_calls[0].tool_name == "explain_budget_overrun"


def test_supervisor_routes_purchase_simulation(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Toi mua dien thoai 15 trieu thang nay co on khong?")))

    assert response.tool_calls[0].tool_name == "simulate_purchase_impact"
    assert response.tool_calls[0].arguments["amount"] == 15_000_000


def test_supervisor_routes_emergency_fund(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Quy khan cap cua toi du chua?")))

    assert response.tool_calls[0].tool_name == "get_emergency_fund_status"


def test_supervisor_routes_debt_summary(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Toi con khoan no tra gop nao khong?")))

    assert response.tool_calls[0].tool_name == "get_debt_summary"


def test_supervisor_routes_recurring_transactions(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Toi co khoan dinh ky nao hang thang?")))

    assert response.tool_calls[0].tool_name == "get_recurring_transactions"


def test_supervisor_routes_cashflow_calendar(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)

    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Ngay nao toi de thieu tien tu gio toi cuoi thang?")))

    assert response.tool_calls[0].tool_name == "get_cashflow_calendar"
