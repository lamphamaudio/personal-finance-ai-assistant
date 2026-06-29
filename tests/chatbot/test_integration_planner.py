import asyncio
import json
import re
from datetime import date
import pytest
import httpx
from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest, ToolExecutionResult
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


@pytest.fixture(autouse=True)
def mock_today(monkeypatch):
    monkeypatch.setattr(
        "spectra.chat.insight_tools.get_today_in_user_timezone",
        lambda tz_str="Asia/Ho_Chi_Minh": date(2026, 6, 24)
    )
    monkeypatch.setattr(
        "spectra.chat.supervisor.get_today_in_user_timezone",
        lambda tz_str="Asia/Ho_Chi_Minh": date(2026, 6, 24)
    )


async def _fake_execute(self, tool_name, arguments=None, **kwargs):
    data_by_tool = {
        "compare_period_spending": {
            "totals": {"period_a_spent": 2_000_000, "period_b_spent": 1_500_000, "spent_delta": 500_000},
            "category_deltas": [{"category": "Food", "delta": 300_000}],
            "limitations": []
        },
        "get_account_summary": {
            "total_spent": 1_250_000,
            "total_income": 3_000_000,
            "currency": "VND",
            "transaction_count": 46,
            "uncategorized": 10,
            "by_category": {"Ăn uống": 750_000},
            "selected_period": {"label": "Tháng 4/2026"},
            "has_data": True,
        }
    }
    return ToolExecutionResult(tool_name=tool_name, status="success", data=data_by_tool.get(tool_name, {}))


@pytest.fixture(autouse=True)
def mock_executor(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_execute)


@pytest.fixture(autouse=True)
def mock_openai_api(monkeypatch):
    def mock_send(self, request, **kwargs):
        content_str = request.content.decode("utf-8")
        payload = json.loads(content_str)
        messages = payload.get("messages", [])
        
        system_msg = next((msg["content"] for msg in messages if msg["role"] == "system"), "")
        user_msg = next((msg["content"] for msg in messages if msg["role"] == "user"), "")
        
        # These structural assertions only apply to the planner call, which injects date/tool
        # rules into the user message. The synthesis call has a different user message format.
        is_planner_call = "TOOL SELECTION RULES" in user_msg
        if is_planner_call:
            assert "DATE RANGE RULES" in user_msg, "Prompt missing DATE RANGE RULES in user message context"
            assert "2026-06-24" in user_msg, "Prompt missing today's date 2026-06-24 in user message context"
            assert "TOOL SELECTION RULES" not in system_msg, "Duplicate injection: TOOL SELECTION RULES in system message"
            assert "DATE RANGE RULES" not in system_msg, "Duplicate injection: DATE RANGE RULES in system message"
        
        # Extract only the actual user question from the prompt template.
        # user_msg contains the full built prompt (with TOOL SELECTION RULES examples
        # that include comparison phrases like "tháng này với tháng trước"), so checking
        # user_msg.lower() directly causes false-positive routing. Instead, extract just
        # the raw message after the "Cau hoi cua nguoi dung:" label.
        query_match = re.search(r"Cau hoi cua nguoi dung:\s*(.+?)(?:\n|$)", user_msg)
        user_query = (query_match.group(1).strip() if query_match else user_msg).lower()
        mock_plan = {}

        if "nhiều hơn tháng 3" in user_query or "thang 4 tieu nhieu hon" in user_query:
            mock_plan = {
                "thought": "So sánh chi tiêu tháng 4 với tháng 3.",
                "plan": [
                    {
                        "id": "1",
                        "tool_name": "compare_period_spending",
                        "arguments": {
                            "period_a_from": "2026-04-01",
                            "period_a_to": "2026-05-01",
                            "period_b_from": "2026-03-01",
                            "period_b_to": "2026-04-01"
                        },
                        "depends_on": [],
                        "requires_confirmation": False
                    }
                ],
                "direct_response": None
            }
        elif "tháng này với tháng trước" in user_query or "thang nay voi thang truoc" in user_query:
            mock_plan = {
                "thought": "So sánh tháng này với tháng trước.",
                "plan": [
                    {
                        "id": "1",
                        "tool_name": "compare_period_spending",
                        "arguments": {
                            "period_a_from": "2026-06-01",
                            "period_a_to": "2026-06-25",
                            "period_b_from": "2026-05-01",
                            "period_b_to": "2026-06-01"
                        },
                        "depends_on": [],
                        "requires_confirmation": False
                    }
                ],
                "direct_response": None
            }
        elif "tuần này với tuần trước" in user_query or "tuan nay voi tuan truoc" in user_query:
            mock_plan = {
                "thought": "So sánh tuần này với tuần trước.",
                "plan": [
                    {
                        "id": "1",
                        "tool_name": "compare_period_spending",
                        "arguments": {
                            "period_a_from": "2026-06-22",
                            "period_a_to": "2026-06-29",
                            "period_b_from": "2026-06-15",
                            "period_b_to": "2026-06-22"
                        },
                        "depends_on": [],
                        "requires_confirmation": False
                    }
                ],
                "direct_response": None
            }
        elif "quý 1 so với quý 2" in user_query or "quy 1 so voi quy 2" in user_query:
            mock_plan = {
                "thought": "So sánh quý 1 với quý 2.",
                "plan": [
                    {
                        "id": "1",
                        "tool_name": "compare_period_spending",
                        "arguments": {
                            "period_a_from": "2026-04-01",
                            "period_a_to": "2026-06-25",
                            "period_b_from": "2026-01-01",
                            "period_b_to": "2026-04-01"
                        },
                        "depends_on": [],
                        "requires_confirmation": False
                    }
                ],
                "direct_response": None
            }
        elif "tháng 4 tôi chi bao nhiêu" in user_query or "thang 4 toi chi bao nhieu" in user_query:
            mock_plan = {
                "thought": "Chi tiêu tháng 4.",
                "plan": [
                    {
                        "id": "1",
                        "tool_name": "get_account_summary",
                        "arguments": {
                            "date_from": "2026-04-01",
                            "date_to": "2026-05-01"
                        },
                        "depends_on": [],
                        "requires_confirmation": False
                    }
                ],
                "direct_response": None
            }
        else:
            mock_plan = {
                "thought": "Default mock response",
                "plan": [],
                "direct_response": "Default mock response"
            }
            
        response_payload = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(mock_plan, ensure_ascii=False)
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        }
        
        return httpx.Response(
            status_code=200,
            content=json.dumps(response_payload, ensure_ascii=False).encode("utf-8"),
            request=request
        )
        
    monkeypatch.setattr(httpx.Client, "send", mock_send)


def call_chat(message: str):
    supervisor = ChatSupervisor(_request(), "user-1")
    return asyncio.run(supervisor.respond(ChatRequest(message=message)))


def test_implicit_comparison_uses_compare_tool():
    """
    "tháng 4 tiêu nhiều hơn tháng 3 không?" phải gọi compare_period_spending
    với cả period_a (tháng 4) và period_b (tháng 3), không phải get_account_summary.
    """
    response = call_chat("tháng 4 tiêu nhiều hơn tháng 3 không?")
    tool_names = [t.tool_name for t in response.tool_calls]
    assert "compare_period_spending" in tool_names
    assert "get_account_summary" not in tool_names
    compare_args = next(t for t in response.tool_calls
                        if t.tool_name == "compare_period_spending").arguments
    assert compare_args["period_a_from"] == "2026-04-01"
    assert compare_args["period_b_from"] == "2026-03-01"


def test_explicit_comparison_this_vs_last_month():
    """
    "so sánh tháng này với tháng trước" phải gọi compare_period_spending.
    """
    response = call_chat("so sánh tháng này với tháng trước")
    tool_names = [t.tool_name for t in response.tool_calls]
    assert "compare_period_spending" in tool_names
    compare_args = next(t for t in response.tool_calls
                        if t.tool_name == "compare_period_spending").arguments
    assert compare_args["period_a_from"] == "2026-06-01"
    assert compare_args["period_b_from"] == "2026-05-01"


def test_weekly_comparison_correct_7_day_range():
    """
    "so sánh tuần này với tuần trước": mỗi period phải đủ 7 ngày.
    today=2026-06-24 (thứ Tư) → tuần này: 06-22→06-29, tuần trước: 06-15→06-22
    """
    response = call_chat("so sánh tuần này với tuần trước")
    args = next(t for t in response.tool_calls
                if t.tool_name == "compare_period_spending").arguments
    period_a_days = (date.fromisoformat(args["period_a_to"])
                     - date.fromisoformat(args["period_a_from"])).days
    period_b_days = (date.fromisoformat(args["period_b_to"])
                     - date.fromisoformat(args["period_b_from"])).days
    assert period_a_days == 7, f"Tuần này phải 7 ngày, got {period_a_days}"
    assert period_b_days == 7, f"Tuần trước phải 7 ngày, got {period_b_days}"


def test_quarterly_comparison_correct_exclusive_end():
    """
    "quý 1 so với quý 2": Q1 phải to=2026-04-01 (không phải 03-31).
    Q1 không bị MTD-align dù Q2 chưa kết thúc.
    """
    response = call_chat("chi tiêu quý 1 so với quý 2 năm nay thế nào?")
    args = next(t for t in response.tool_calls
                if t.tool_name == "compare_period_spending").arguments
    dates = {
        "period_a_from": args["period_a_from"],
        "period_a_to":   args["period_a_to"],
        "period_b_from": args["period_b_from"],
        "period_b_to":   args["period_b_to"],
    }
    # Xác định Q1 và Q2 từ dates (không phụ thuộc Planner gửi thứ tự nào)
    q1_from = "2026-01-01"
    q1_to   = "2026-04-01"   # exclusive end đúng
    if dates["period_a_from"] == q1_from:
        assert dates["period_a_to"] == q1_to, (
            f"Q1 period_to phải là 2026-04-01, got {dates['period_a_to']}"
        )
    else:
        assert dates["period_b_from"] == q1_from
        assert dates["period_b_to"] == q1_to, (
            f"Q1 period_to phải là 2026-04-01, got {dates['period_b_to']}"
        )


def test_single_period_query_uses_summary_tool():
    """
    "tháng 4 tôi chi bao nhiêu?" chỉ hỏi 1 period → get_account_summary.
    """
    response = call_chat("tháng 4 tôi chi bao nhiêu?")
    tool_names = [t.tool_name for t in response.tool_calls]
    assert "get_account_summary" in tool_names
    assert "compare_period_spending" not in tool_names
