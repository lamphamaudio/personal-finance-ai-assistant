import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_supervisor_routes_financial_health_question(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "score": 72,
                "level": "Trung binh kha",
                "period": {"label": "June 2026"},
                "strengths": ["Dong tien van duong."],
                "risks": ["Co 2 giao dich bat thuong can kiem tra."],
                "recommended_actions": ["Kiem tra lai cac giao dich bat thuong trong ky."],
                "missing_data": [],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="Tai chinh cua toi co on khong?")))

    assert response.intent == "FINANCIAL_HEALTH_SCORE"
    assert response.tool_calls[0].tool_name == "get_financial_health_score"
    assert "72/100" in response.answer
    assert "user-1" not in response.answer
    assert "khong phai diem tin dung" in response.answer
