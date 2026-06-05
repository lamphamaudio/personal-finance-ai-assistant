import asyncio
from datetime import date

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest, ToolExecutionResult
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_summary_period_parser_uses_current_year_for_month_number():
    period = ChatSupervisor._parse_summary_period("Tong chi va thu trong thang 5", today=date(2026, 6, 4))

    assert period == {"date_from": "2026-05-01", "date_to": "2026-06-01"}


def test_supervisor_routes_monthly_cashflow_summary_to_account_summary(monkeypatch):
    captured = {}

    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        captured.update({"tool_name": tool_name, "arguments": arguments or {}})
        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "total_spent": 1_250_000,
                "total_income": 3_000_000,
                "currency": "VND",
                "transaction_count": 46,
                "uncategorized": 10,
                "by_category": {"Ăn uống": 750_000},
                "selected_period": {"label": "Tháng 5/2026"},
                "has_data": True,
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)

    response = asyncio.run(
        ChatSupervisor(_request(), "user-1").respond(
            ChatRequest(message="tổng chi và thu trong tháng 5 là bao nhiêu?")
        )
    )

    assert response.intent == "SPENDING_BREAKDOWN"
    assert captured["tool_name"] == "get_account_summary"
    assert captured["arguments"]["date_from"].endswith("-05-01")
    assert captured["arguments"]["date_to"].endswith("-06-01")
    assert "46 giao dịch" in response.answer
    assert "1,250,000 VND" in response.answer
    assert "3,000,000 VND" in response.answer
