"""OpenAI-backed chatbot supervisor with Phase 3 confirmation flows."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any, Literal, TypedDict
from langgraph.graph import StateGraph, END
from fastapi import Request

from spectra.categories import CATEGORIES, normalize_category
from spectra.chat.confirmation import PendingAction, pending_actions
from spectra.chat.executor import ToolExecutor
from spectra.chat.memory import extract_memory_candidates, get_session_state, save_session_state, upsert_user_memory
from spectra.chat.models import ChatConfirmation, ChatIntent, ChatRequest, ChatResponse, ChatToolCallTrace, SuggestedAction
from spectra.chat.prompts import FINALIZER_SYSTEM_PROMPT, SUPERVISOR_SYSTEM_PROMPT
from spectra.chat.redaction import redact_payload, redact_text
from spectra.chat.tools import openai_tool_definitions
from spectra.config import Settings, load_settings
from spectra.chat.insight_tools import get_today_in_user_timezone

logger = logging.getLogger("spectra.chat")

_SAFE_DEFAULT_MODEL = "gpt-4o-mini"
_UNSUPPORTED_KEYWORDS: dict[ChatIntent, list[str]] = {}
_INVESTMENT_KEYWORDS = ["mua co phieu", "ban co phieu", "crypto", "coin", "chung khoan", "buy stock", "sell stock"]
_LAST_CATEGORY_CORRECTIONS: dict[str, dict[str, Any]] = {}
_LAST_CATEGORY_CANDIDATES: dict[str, dict[str, Any]] = {}
_LAST_SAVINGS_PLAN: dict[str, dict[str, Any]] = {}
_LAST_BUDGET_PLAN: dict[str, list[dict[str, Any]]] = {}
_FINALIZER_MAX_CHARS = 1200
_FINALIZER_BLOCKED_RE = re.compile(
    r"(?i)(sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._~+/=-]{12,}|"
    r"openai_api_key|api_key|password|session_token|access_token|"
    r"\buser_id\b|\baccount_number\b|\breference_number\b|system prompt|tool_name)"
)
_FINALIZER_TOOL_NAME_RE = re.compile(
    r"\b(?:get|update|create|archive|remember|forget|simulate|recommend|compare|plan)_[a-z0-9_]+\b",
    re.IGNORECASE,
)
_RAW_LONG_IDENTIFIER_RE = re.compile(r"\b\d{10,19}\b")
_UUID_IN_TEXT_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class SubTask(TypedDict):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    depends_on: list[str]
    requires_confirmation: bool


class AgentState(TypedDict):
    message: str
    session_id: str | None
    user_id: str
    scope: Literal["cycle", "90d", "ytd"]
    debug: bool
    confirmation_id: str | None
    confirm: bool | None
    early_return: bool
    response: ChatResponse | None
    execution_plan: list[SubTask] | None
    tool_results: list[dict[str, Any]]
    tool_calls: list[ChatToolCallTrace]
    synthesized_by_llm: bool


class MissingOpenAIKeyError(RuntimeError):
    pass


class ChatSupervisor:
    def __init__(
        self,
        request: Request,
        user_id: str,
        settings: Settings | None = None,
        *,
        session_id: str | None = None,
        chat_context: dict[str, Any] | None = None,
    ):
        self.request = request
        self.user_id = user_id
        self.settings = settings or load_settings()
        self.executor = ToolExecutor(request, user_id)
        self.session_id = str(session_id or "").strip() or None
        self.chat_context = chat_context or {}

    async def respond(self, chat_request: ChatRequest) -> ChatResponse:
        from spectra.chat.tracing import start_trace
        inputs = {
            "message": chat_request.message,
            "session_id": chat_request.session_id,
            "scope": chat_request.scope,
            "confirmation_id": chat_request.confirmation_id,
            "confirm": chat_request.confirm,
        }
        with start_trace(
            user_id=self.user_id,
            session_id=self.session_id,
            name="chat_request",
            inputs=inputs,
        ) as root_rec:
            # 1. Run Input Guardrails
            from spectra.chat.guardrails.engine import guardrail_engine
            early_input = guardrail_engine.check_input(chat_request.message)
            if early_input:
                root_rec.outputs = {"answer": early_input.answer, "intent": early_input.intent.value}
                return early_input

            # 2. Get inner response
            response = await self._respond_inner(chat_request)

            # 3. Run Output Guardrails
            response.answer = guardrail_engine.check_output(response.answer, response.intent.value)
            
            root_rec.outputs = {
                "answer": response.answer,
                "intent": response.intent.value,
                "tool_calls": [
                    {"tool_name": t.tool_name, "arguments": t.arguments, "status": t.status, "error": t.error}
                    for t in response.tool_calls
                ]
            }
            return response

    async def _respond_inner(self, chat_request: ChatRequest) -> ChatResponse:
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("input_guard", self._input_guard_node)
        workflow.add_node("confirmation", self._confirmation_node)
        workflow.add_node("deterministic", self._deterministic_node)
        workflow.add_node("fast_path", self._fast_path_node)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("synthesis", self._synthesis_node)
        workflow.add_node("finalizer", self._finalizer_node)
        workflow.add_node("output_guard", self._output_guard_node)
        
        # Set entry point
        workflow.set_entry_point("input_guard")
        
        # Define routes
        def route_input_guard(state: AgentState) -> str:
            if state.get("early_return"):
                return "output_guard"
            return "confirmation"
            
        def route_confirmation(state: AgentState) -> str:
            if state.get("early_return"):
                return "output_guard"
            return "deterministic"
            
        def route_deterministic(state: AgentState) -> str:
            if state.get("early_return"):
                return "output_guard"
            return "fast_path"
            
        def route_fast_path(state: AgentState) -> str:
            if state.get("early_return"):
                return "output_guard"
            return "planner"
            
        def route_synthesis(state: AgentState) -> str:
            resp = state.get("response")
            # The LLM synthesis path already wrote a complete, multi-intent answer;
            # skip the finalizer's second rewrite (saves one LLM call) and go straight
            # to the output guard. Only single-tool legacy formatters need finalizing.
            if state.get("synthesized_by_llm"):
                return "output_guard"
            if resp and not resp.requires_confirmation and resp.tool_calls:
                return "finalizer"
            return "output_guard"
            
        # Add conditional edges
        workflow.add_conditional_edges("input_guard", route_input_guard)
        workflow.add_conditional_edges("confirmation", route_confirmation)
        workflow.add_conditional_edges("deterministic", route_deterministic)
        workflow.add_conditional_edges("fast_path", route_fast_path)
        
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "synthesis")
        
        workflow.add_conditional_edges("synthesis", route_synthesis)
        workflow.add_edge("finalizer", "output_guard")
        workflow.add_edge("output_guard", END)
        
        # Compile graph
        graph = workflow.compile()
        
        # Run graph
        initial_state = AgentState(
            message=chat_request.message,
            session_id=chat_request.session_id,
            user_id=self.user_id,
            scope=chat_request.scope,
            debug=chat_request.debug,
            confirmation_id=chat_request.confirmation_id,
            confirm=chat_request.confirm,
            early_return=False,
            response=None,
            execution_plan=None,
            tool_results=[],
            tool_calls=[],
            synthesized_by_llm=False,
        )
        
        try:
            final_state = await graph.ainvoke(initial_state)
            return final_state.get("response") or ChatResponse(
                answer="Xin loi, minh chua the hoan thanh yeu cau.",
                intent=ChatIntent.UNKNOWN
            )
        except Exception:
            logger.exception("LangGraph execution failed")
            return ChatResponse(
                answer="Xin loi, hien minh chua the xu ly cau hoi nay. Vui long thu lai sau.",
                intent=ChatIntent.UNKNOWN,
                tool_calls=[],
            )

    async def _input_guard_node(self, state: AgentState) -> dict[str, Any]:
        from spectra.chat.guardrails.engine import guardrail_engine
        early_input = guardrail_engine.check_input(state["message"])
        if early_input:
            return {"response": early_input, "early_return": True}
        return {"early_return": False}

    async def _confirmation_node(self, state: AgentState) -> dict[str, Any]:
        req = ChatRequest(
            message=state["message"],
            session_id=state["session_id"],
            scope=state["scope"],
            debug=state["debug"],
            confirmation_id=state["confirmation_id"],
            confirm=state["confirm"]
        )
        confirmation_response = await self._handle_confirmation_request(req)
        if confirmation_response:
            return {"response": confirmation_response, "early_return": True}
        return {"early_return": False}

    async def _deterministic_node(self, state: AgentState) -> dict[str, Any]:
        req = ChatRequest(
            message=state["message"],
            session_id=state["session_id"],
            scope=state["scope"],
            debug=state["debug"],
            confirmation_id=state["confirmation_id"],
            confirm=state["confirm"]
        )
        deterministic = self._handle_phase3_category_flow(req)
        if deterministic:
            return {"response": deterministic, "early_return": True}
        return {"early_return": False}

    async def _fast_path_node(self, state: AgentState) -> dict[str, Any]:
        req = ChatRequest(
            message=state["message"],
            session_id=state["session_id"],
            scope=state["scope"],
            debug=state["debug"],
            confirmation_id=state["confirmation_id"],
            confirm=state["confirm"]
        )
        normalized = self._fold(state["message"])

        # "lên kế hoạch ngân sách" is a single budget-planning intent even though the message also
        # contains "tiết kiệm" + "thu nhập", which would falsely trigger _is_multi_intent.
        # Intercept it deterministically before the multi-intent gate.
        if "ngan sach" in normalized and any(t in normalized for t in ["len ke hoach", "ke hoach ngan sach", "lap ke hoach"]):
            budget_resp = await self._handle_phase7_budget_flow(req, normalized)
            if budget_resp:
                return {"response": budget_resp, "early_return": True}

        # A compound, multi-intent question must not be answered by a single
        # deterministic handler (which would address only one part). Send it to the
        # planner so it can be decomposed into several tool calls and synthesized.
        if self._is_multi_intent(state["message"], normalized):
            return {"execution_plan": None}
        phase4_resp = await self._handle_phase4_read_flow(req)
        if phase4_resp:
            return {"response": phase4_resp, "early_return": True}
        return {"execution_plan": None}

    def _build_clarification_response(
        self, question: str, suggestions: list[dict[str, str]] | None = None
    ) -> ChatResponse:
        """Build a clarification response: a short question plus clickable suggestion chips.

        Each suggestion chip carries an `arguments.message` so the frontend re-sends it as the
        user's next message (see ChatPanel SuggestedActions onSend handling).
        """
        actions: list[SuggestedAction] = []
        for item in (suggestions or [])[:4]:
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            message = str(item.get("message") or label).strip()
            actions.append(
                SuggestedAction(label=label, type="prompt", arguments={"message": message})
            )
        return ChatResponse(
            answer=question,
            intent=ChatIntent.CLARIFICATION_NEEDED,
            suggested_actions=actions,
        )

    def _clarification_for_missing_data(
        self, tool_name: str, data: dict[str, Any], message: str
    ) -> ChatResponse | None:
        """Reactive clarification: a planning tool ran but reported a blocking data gap.

        Returns a clarification response when the missing field makes the result unusable,
        otherwise None so the normal formatter runs.
        """
        _PLANNING_TOOLS = {
            "recommend_budget_plan",
            "plan_savings_goal",
            "get_budget_status",
            "simulate_budget_adjustment",
        }
        if tool_name not in _PLANNING_TOOLS or not isinstance(data, dict):
            return None
        missing = {str(item) for item in (data.get("missing_data") or [])}
        if "income" in missing:
            return self._build_clarification_response(
                "Để tính chính xác mình cần biết thu nhập hàng tháng của bạn khoảng bao nhiêu?",
                [
                    {"label": "Khoảng 15 triệu", "message": "thu nhập của tôi khoảng 15 triệu/tháng"},
                    {"label": "Khoảng 20 triệu", "message": "thu nhập của tôi khoảng 20 triệu/tháng"},
                    {
                        "label": "Ước lượng từ lịch sử giao dịch của tôi",
                        "message": "hãy ước lượng thu nhập của tôi từ lịch sử giao dịch",
                    },
                ],
            )
        if "budget_limits" in missing:
            return self._build_clarification_response(
                "Bạn chưa đặt hạn mức ngân sách nào. Bạn muốn mình đề xuất hạn mức hay bạn tự đặt?",
                [
                    {"label": "Đề xuất ngân sách cho tôi", "message": "hãy đề xuất ngân sách cho tôi"},
                    {"label": "Tôi tự đặt hạn mức", "message": "tôi muốn tự đặt hạn mức ngân sách"},
                ],
            )
        return None

    @staticmethod
    def _missing_required_field(error: str | None) -> str | None:
        """Extract the missing field name from a jsonschema 'required property' error."""
        if not error:
            return None
        match = re.search(r"'([^']+)' is a required property", error)
        return match.group(1) if match else None

    async def _planner_node(self, state: AgentState) -> dict[str, Any]:
        if state["execution_plan"] is not None:
            return {}

        api_key = self.settings.openai_api_key
        if not api_key:
            raise MissingOpenAIKeyError("OPENAI_API_KEY is missing")

        req = ChatRequest(
            message=state["message"],
            session_id=state["session_id"],
            scope=state["scope"],
            debug=state["debug"]
        )

        client = self._make_openai_client(api_key, timeout=30.0)
        model = self.settings.openai_model or _SAFE_DEFAULT_MODEL

        planner_instructions = """
You are Personal Finance AI Assistant v3. Your task is to analyze the user's Vietnamese query and construct a structured Execution Plan to answer it using the available tools.

You have access to the following 38 tools:
1. get_current_user: Return the authenticated user context.
2. get_account_summary: Return aggregate spending, income, category, and merchant summary (takes scope, and optional date_from, date_to).
3. get_transactions: Return transaction rows (takes page, per_page, category, uncategorized_only, search, date_from, date_to).
4. get_category_options: Return transaction category options.
5. update_transaction_category: Update a transaction category (requires confirmation) (takes tx_id, category, and optional apply_to_future).
6. test_category_rule: Preview whether a category rule matches (takes pattern, and optional rule_type, sample_text).
7. create_category_rule: Create a category memory rule (requires confirmation) (takes pattern, category, and optional rule_type).
8. get_category_rules: Return active category rules.
9. get_learning_summary: Return category learning summary.
10. get_anomalies: Return unusual/suspicious financial activities (takes optional limit, scope).
11. explain_anomaly: Explain why a specific anomaly is unusual (takes anomaly_id).
12. get_balance_forecast: Return end-of-month forecast and spending trend (takes optional scope).
13. get_financial_health_score: Return cashflow and budgeting health score (takes optional scope, month).
14. plan_savings_goal: Calculate savings goal feasibility (takes name, target_amount, current_amount, target_date).
15. simulate_savings_adjustment: Simulate spending reduction to reach goal (takes target_amount, current_amount, target_date, adjustments).
16. get_savings_goals: Return active/archived/completed saving goals (takes optional status).
17. create_savings_goal: Create a saving goal (requires confirmation) (takes name, target_amount, current_amount, target_date).
18. update_savings_goal: Update a saving goal (requires confirmation) (takes goal_id, and optional name, target_amount, current_amount, target_date, status).
19. archive_savings_goal: Archive a saving goal (requires confirmation) (takes goal_id).
20. get_budget_status: Return budget limits, actuals, remaining, and overrun risks (takes optional scope).
21. recommend_budget_plan: Recommend a category-level budget plan (takes optional scope, goal_id, target_savings_amount, monthly_income).
22. simulate_budget_adjustment: Simulate impact of custom budget limit changes (takes adjustments, and optional scope, goal_id).
23. compare_budget_vs_actual: Compare actual spending with budget limits (takes optional scope).
24. update_budget_limit: Update a category budget limit (requires confirmation) (takes category, limit).
25. upsert_budget_plan: Create or update multiple budget limits (requires confirmation) (takes budgets).
26. get_recurring_transactions: Return subscription/recurring payment info (takes optional scope, limit).
27. compare_period_spending: Compare spending/income between periods or months (takes optional period_a_from, period_a_to, period_b_from, period_b_to).
28. explain_budget_overrun: Explain overrun categories and transactions (takes optional scope, category).
29. get_cashflow_calendar: Return daily cashflow projection calendar (takes optional days).
30. simulate_purchase_impact: Simulate a future purchase impact on budget/forecast (takes amount, and optional category, purchase_date, scope).
31. get_debt_summary: Infer debt-like payments from transactions (takes optional scope).
32. get_emergency_fund_status: Estimate emergency fund coverage months (takes optional months_target).
33. simulate_income_change: Simulate the impact of a monthly income increase or decrease on surplus, savings rate, and goal feasibility (takes income_delta in VND, and optional scope). Use for "nếu tăng/giảm lương X thì sao", "nếu thu nhập thêm Xtr".
34. get_spending_patterns: Analyze historical spending patterns grouped by weekday, day of month, or week of month (takes optional scope, group_by). Use for "cuối tuần hay ngày thường", "ngày nào tiêu nhiều nhất", "tuần nào tiêu nhiều nhất".
35. get_conversation_context: Return conversation history context (takes session_id).
36. get_user_memories: Return saved user memories (takes optional memory_types).
37. remember_user_preference: Remember a preference (requires confirmation) (takes key, value, reason, and optional memory_type).
38. forget_user_memory: Delete a preference (requires confirmation) (takes memory_id).
39. get_peer_benchmark: Compare the user's needs/wants/savings allocation against reference benchmarks (50/30/20 and income-bracket norms) (takes optional scope, monthly_income_override). Use for peer/social comparison: "so sánh với người cùng tuổi/cùng địa vị xã hội", "chi tiêu của tôi đã hợp lý chưa", "người có lương X thường chi bao nhiêu". Does NOT use other users' real data.

Write Tools:
The following tools are write tools and change settings, budgets, or goals. They ALWAYS require explicit confirmation before execution:
- update_transaction_category
- create_category_rule
- create_savings_goal
- update_savings_goal
- archive_savings_goal
- update_budget_limit
- upsert_budget_plan
- remember_user_preference
- forget_user_memory

You MUST return a JSON object with this exact structure:
{
  "thought": "Your reasoning in Vietnamese",
  "plan": [
    {
      "id": "1",
      "tool_name": "name_of_tool",
      "arguments": { ... },
      "depends_on": [],
      "requires_confirmation": false
    }
  ],
  "direct_response": "Your Vietnamese response here if no tools are needed, otherwise null",
  "clarification": null
}

CLARIFICATION RULE (ask back instead of guessing):
- Only when guessing would likely produce a WRONG or USELESS answer, set "clarification" to an object and leave "plan" empty + "direct_response" null:
  { "clarification": { "question": "<câu hỏi ngắn tiếng Việt>", "suggestions": [ {"label": "<nhãn nút>", "message": "<câu user sẽ gửi khi bấm>"}, ... ] } }
- Provide 2-4 concrete suggestions. If a reasonable default exists, DO NOT ask — just run the tools.
- Apply in these cases:
  1. A REQUIRED argument for the needed tool is missing and cannot be inferred. Example: "tạo mục tiêu tiết kiệm" but no số tiền or thời hạn → hỏi mục tiêu cần bao nhiêu và trong bao lâu (gợi ý ví dụ "20 triệu trong 6 tháng").
  2. The request is too VAGUE/BROAD to map to a specific analysis. Example: "giúp tôi quản lý tài chính", "tôi nên làm gì với tiền của mình" → hỏi muốn xem mảng nào, gợi ý: "Xem tổng quan chi tiêu", "Đánh giá sức khỏe tài chính", "Lập kế hoạch ngân sách".
  3. The TIME PERIOD is genuinely unspecified AND the question is sensitive to it. Example: "tôi chi tiêu nhiều không?" with no time hint → gợi ý: "Tháng này", "90 ngày gần đây", "Từ đầu năm". BUT if the message already contains a time signal ("tháng này", "6 tháng", "tuần này", a concrete date), DO NOT ask — proceed with the matching date window.
- If a write tool requires confirmation, NEVER use clarification; the confirmation flow handles it.

MULTI-INTENT DECOMPOSITION (IMPORTANT):
- A single Vietnamese message often contains SEVERAL sub-questions joined by words like "và", "rồi", "đồng thời", "với lại", "ngoài ra", "còn", or multiple "?".
- Break the message into its sub-questions and create ONE task per sub-question, preserving the user's order. Do NOT answer only the first part.
- Pick the most specific tool for each sub-question. If one sub-question needs the result of another, use "depends_on" and reference it with "$id.field_name".
- Worked example 1 — message: "6 tháng gần nhất tôi chi tiêu bao nhiêu, và với lương 18tr thì 5 năm tôi muốn để dành 500tr thì mỗi tháng cần đưa bao nhiêu vào tài khoản?"
  Decompose into two tasks:
    {"id":"1","tool_name":"get_account_summary","arguments":{"date_from":"<first day 6 months ago>","date_to":"<first day of next month>"},"depends_on":[],"requires_confirmation":false}
    {"id":"2","tool_name":"plan_savings_goal","arguments":{"name":"Mục tiêu tiết kiệm","target_amount":500000000,"current_amount":0,"target_date":"<today + 5 years>"},"depends_on":[],"requires_confirmation":false}
  (The synthesis step will then combine both results into one answer.)
- Worked example 2 — message: "Tháng này tôi tiêu nhiều nhất vào đâu và cuối tháng tôi còn lại bao nhiêu?"
  Decompose into two tasks:
    {"id":"1","tool_name":"get_account_summary","arguments":{"date_from":"<first day of current month>","date_to":"<first day of next month>"},"depends_on":[],"requires_confirmation":false}
    {"id":"2","tool_name":"get_balance_forecast","arguments":{"scope":"current_month"},"depends_on":[],"requires_confirmation":false}
- Worked example 3 — message: "6 tháng gần nhất tôi chi tiêu bao nhiêu và tài chính của tôi hiện tại có ổn không?"
  Decompose into two tasks:
    {"id":"1","tool_name":"get_account_summary","arguments":{"date_from":"<first day 6 months ago>","date_to":"<first day of next month>"},"depends_on":[],"requires_confirmation":false}
    {"id":"2","tool_name":"get_financial_health_score","arguments":{},"depends_on":[],"requires_confirmation":false}

SPENDING SUMMARY vs COMPARISON — never confuse these:
- "N tháng gần nhất/gần đây tôi chi tiêu bao nhiêu?" = SUMMARY of ONE date window → use `get_account_summary` with date_from/date_to covering that window.
  Example: "6 tháng gần nhất" → date_from = <first day 6 months ago>, date_to = <first day of next month>.
- "So sánh tháng này với tháng trước", "chi tiêu có tăng không?", "khác gì tháng trước?" = COMPARE two distinct periods → use `compare_period_spending`.
- RULE: `compare_period_spending` is ONLY for comparing TWO periods against each other. A single time-range spending query ALWAYS uses `get_account_summary`. When in doubt, default to `get_account_summary`.

PEER COMPARISON (không phải period comparison):
- Khi user hỏi "so sánh với người cùng tuổi", "người có lương X thường chi bao nhiêu", "cùng địa vị xã hội",
  "mức trung bình xã hội", "chi tiêu của tôi đã hợp lý chưa", "tôi tiêu nhiều hơn người khác không" → get_peer_benchmark.
- KHÔNG dùng compare_period_spending cho peer comparison. Đó là so sánh 2 kỳ thời gian, hoàn toàn khác.
- get_peer_benchmark so cơ cấu chi tiêu (needs/wants/savings) của user với chuẩn 50/30/20 và mức kỳ vọng theo nhóm thu nhập.
  LƯU Ý: đây là chuẩn tham chiếu chung, KHÔNG phải dữ liệu người dùng thật — khi tổng hợp câu trả lời hãy nói rõ điều này.
- Ví dụ: "So với người cùng độ tuổi thì chi tiêu của tôi đã hợp lý chưa?" → get_peer_benchmark()

PURCHASE FEASIBILITY — "có thể mua X không?", "nên mua X không?":
- Khi user hỏi "có thể mua X [số tiền] không?", "nên mua X không?", "mua X [số tiền] có ổn không?" → simulate_purchase_impact(amount=X).
- Ví dụ: "Tôi có thể mua iPhone 25 triệu vào tuần sau không?" → simulate_purchase_impact(amount=25000000, category="Điện tử")
- KHÔNG dùng get_account_summary hoặc get_cashflow_calendar thay thế — chúng không trả lời được câu hỏi "có thể mua được không".
- Nếu user tiếp tục hỏi "nếu không thì cần cắt ở đâu?" → thêm task explain_budget_overrun hoặc get_budget_status.

SPENDING REDUCTION BY PERCENTAGE — "giảm X% chi tiêu", "cắt X%":
- Khi user hỏi "muốn giảm chi tiêu X%", "cắt X% chi tiêu", "giảm xuống còn X%" → cần 2 bước:
  Bước 1: get_account_summary() để lấy top categories và tổng chi tiêu.
  Bước 2: simulate_budget_adjustment với adjustments dựa trên top categories, mỗi mục giảm tương ứng X%.
- Ví dụ — "Tôi muốn giảm chi tiêu xuống 20%, cần cắt ở những mục nào?":
  Task 1: {"id":"1","tool_name":"get_account_summary","arguments":{},"depends_on":[]}
  Task 2: {"id":"2","tool_name":"simulate_budget_adjustment","arguments":{"adjustments":[{"category":"Ăn uống","limit":2560000},{"category":"Mua sắm","limit":1920000}]},"depends_on":["1"]}
- KHÔNG để "direct_response" mà không gọi tool — user cần con số cụ thể từ dữ liệu của họ.

SAVINGS RATE QUESTIONS — "bao nhiêu % thu nhập", "tiết kiệm X% thu nhập":
- "Muốn tiết kiệm 100tr trong 2 năm, cần bao nhiêu % thu nhập?" →
    Task 1: plan_savings_goal(name=..., target_amount=100000000, target_date=...)
    Task 2: get_account_summary() để lấy monthly_income
    Tổng hợp: savings_pct = monthly_required / monthly_income × 100
- "Nếu muốn tiết kiệm 30% thu nhập, lên kế hoạch ngân sách" (không có income cụ thể) →
    Task 1: get_account_summary() để lấy monthly_income từ lịch sử
    Task 2: recommend_budget_plan với target_savings_amount ước tính (income × pct, ví dụ 15tr × 30% = 4500000)
    Ví dụ: {"id":"1","tool_name":"get_account_summary","arguments":{},"depends_on":[]}
            {"id":"2","tool_name":"recommend_budget_plan","arguments":{"target_savings_amount":4500000},"depends_on":["1"]}
- KHÔNG gọi get_current_user cho câu hỏi tiết kiệm % — get_current_user chỉ trả về thông tin tài khoản, không giúp tính ngân sách.
- KHÔNG trả lời "direct_response" không có tool — cần dữ liệu thực của user.

SAVINGS TO BUY — "tiết kiệm để mua", "lên lịch tiết kiệm", "để dành mua", "bao lâu thì mua được":
- Khi user hỏi "cần bao lâu/bao nhiêu tháng để tiết kiệm đủ mua X", "lên lịch tiết kiệm trong X tháng để mua",
  "để dành X tháng mua được không", "mỗi tháng cần để ra bao nhiêu để mua X"
  → dùng plan_savings_goal(name="Mua <X>", target_amount=<giá X>, current_amount=0, target_date=<hôm nay + thời gian>)
- KHÔNG dùng simulate_purchase_impact — tool đó chỉ mô phỏng mua NGAY, không phải kế hoạch tiết kiệm tương lai.
- Nếu user refer tới món hàng/số tiền từ tin nhắn trước bằng đại từ ("mua được", "cái đó", "nó", "món đó"),
  lấy target_amount từ ngữ cảnh hội thoại (context). KHÔNG tự bóc số từ chuỗi "X tháng" làm amount.
- Ví dụ — "bạn có thể lên lịch tiết kiệm cho tôi trong 5 tháng để tôi mua được không" (context: laptop 30tr):
  {"id":"1","tool_name":"plan_savings_goal","arguments":{"name":"Mua laptop","target_amount":30000000,"current_amount":0,"target_date":"<hôm nay + 5 tháng>"},"depends_on":[]}
- PHÂN BIỆT rõ:
  • "Tôi có thể mua X ngay bây giờ không?" → simulate_purchase_impact
  • "Tôi cần tiết kiệm bao lâu/bao nhiêu để mua X?" → plan_savings_goal

ADVICE FOR A SPECIFIC CATEGORY — "lời khuyên cắt giảm [danh mục]":
- "Lời khuyên để cắt giảm chi phí ăn uống", "làm sao để tốn ít tiền ăn uống hơn" →
  explain_budget_overrun(category="ăn uống") HOẶC recommend_budget_plan.
- TUYỆT ĐỐI KHÔNG dùng get_recurring_transactions cho câu hỏi "lời khuyên" — đó chỉ dành cho câu hỏi về khoản cố định/subscription.
  get_recurring_transactions chỉ phù hợp khi user hỏi: "khoản định kỳ nào", "subscription nào", "tôi có khoản nào tự động trừ không".
- Ví dụ — "Cho tôi lời khuyên để cắt giảm chi phí ăn uống hàng tháng":
  {"id":"1","tool_name":"explain_budget_overrun","arguments":{"category":"ăn uống"},"depends_on":[]}

GOAL OPERATIONS (archive / update / view a specific goal):
- When the user asks for COMPLETED or ACHIEVED goals (e.g. "mục tiêu đã hoàn thành", "goal nào đã đạt", "lịch sử mục tiêu"):
  → Use get_savings_goals with {"status": "completed"}.
- When the user asks for ARCHIVED goals (e.g. "mục tiêu đã hủy", "đã lưu trữ"):
  → Use get_savings_goals with {"status": "archived"}.
- When the user says "hủy nó", "hủy mục tiêu đó", "xóa goal đó", "cập nhật nó", etc. and the goal_id is NOT explicitly stated:
  → Create a 2-step plan:
    Step 1: {"id":"1","tool_name":"get_savings_goals","arguments":{},"depends_on":[],"requires_confirmation":false}
    Step 2 (archive): {"id":"2","tool_name":"archive_savings_goal","arguments":{"goal_id":"$1.goals.0.id","goal_name":"$1.goals.0.name"},"depends_on":["1"],"requires_confirmation":true}
    Step 2 (update):  {"id":"2","tool_name":"update_savings_goal","arguments":{"goal_id":"$1.goals.0.id","goal_name":"$1.goals.0.name", ...other fields...},"depends_on":["1"],"requires_confirmation":true}
  The "$1.goals.0.id" and "$1.goals.0.name" references are resolved automatically at runtime.
- NEVER fabricate a goal_id like "1", "current_goal_id", "goal_1", or any made-up string. Always use the $ref or an ID the user explicitly states.

CONFIRMATION PLANS (requires_confirmation: true):
- If ANY task in your plan has "requires_confirmation": true, you MUST set "direct_response": null.
- The system handles the confirmation message automatically — do NOT manually ask "Bạn có chắc chắn không?" in direct_response alongside a write plan, or you will create an infinite confirmation loop.

INCOME vs SAVINGS (do not confuse):
- "lương", "thu nhập", "kiếm được", "nhận về" + an amount (e.g. "lương 8tr") = the user's MONTHLY INCOME → pass it as "monthly_income" (8tr = 8000000) to recommend_budget_plan.
- "tiết kiệm", "để dành", "để ra", "muốn dành" + an amount = a SAVINGS target → pass it as "target_savings_amount".
- Never put a salary/income amount into "target_savings_amount".

NO-TOOL RULE (avoid fabricating):
- If a sub-question is general financial knowledge or advice that does NOT need the user's personal data (e.g. "quỹ khẩn cấp nên bằng mấy tháng chi tiêu?", "nguyên tắc 50/30/20 là gì?"), answer it from general knowledge in "direct_response" (when it is the only intent) or rely on synthesis for the compound case — no tool needed.
- If a sub-question NEEDS the user's personal financial numbers but NO tool fits, do NOT invent any number. Create no task for it; the synthesis step will state that part is not supported yet.

Plan construction rules:
- If a task depends on the output of a previous task (e.g. task "2" depends on task "1"), add the ID of the dependency to "depends_on" (e.g., ["1"]). In "arguments", refer to the dependency results using the reference syntax "$id" or "$id.field_name" (e.g., "$1" or "$1.tx_id").
- For write tools, always set "requires_confirmation": true.
- If the user query is a general conversation, explanation, or greeting that does not need database access or financial calculation, set "plan" to [] and write your response in "direct_response".
- Respond in Vietnamese.
"""
        messages = [
            {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT + "\n\n" + planner_instructions},
            {"role": "user", "content": self._build_user_message(req)},
        ]

        from spectra.chat.tracing import trace_span
        with trace_span("openai_planner", "llm", {"model": model, "messages_count": len(messages)}) as span_rec:
            res = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = res.choices[0].message.content or "{}"
            span_rec.outputs = {"content": content}

        try:
            plan_data = json.loads(content)
        except Exception:
            plan_data = {}

        direct_response = plan_data.get("direct_response")
        raw_plan_data = plan_data.get("plan") or []
        has_confirmation_tasks = any(t.get("requires_confirmation") for t in raw_plan_data)

        # Clarification takes priority: the planner decided it needs more info from the user
        # before any tool can run. Mirror the direct_response short-circuit path.
        clarification = plan_data.get("clarification")
        if (
            isinstance(clarification, dict)
            and str(clarification.get("question") or "").strip()
            and not has_confirmation_tasks
        ):
            resp = self._build_clarification_response(
                str(clarification["question"]).strip(),
                clarification.get("suggestions") or [],
            )
            return {"execution_plan": [], "response": resp, "early_return": True}

        if direct_response and not has_confirmation_tasks:
            resp = ChatResponse(
                answer=direct_response,
                intent=ChatIntent.UNKNOWN
            )
            return {"execution_plan": [], "response": resp, "early_return": True}

        raw_plan = plan_data.get("plan", [])
        plan = []
        for task in raw_plan:
            plan.append(
                SubTask(
                    id=str(task.get("id", "")),
                    tool_name=str(task.get("tool_name", "")),
                    arguments=dict(task.get("arguments", {})),
                    depends_on=[str(d) for d in task.get("depends_on", [])],
                    requires_confirmation=bool(task.get("requires_confirmation", False))
                )
            )
        return {"execution_plan": plan}

    async def _executor_node(self, state: AgentState) -> dict[str, Any]:
        plan = state["execution_plan"]
        if not plan:
            return {}

        completed_tasks = {}
        tool_results = list(state["tool_results"])
        tool_calls = list(state["tool_calls"])

        max_waves = 10
        for _ in range(max_waves):
            ready_tasks = []
            for task in plan:
                task_id = task["id"]
                if task_id in completed_tasks:
                    continue
                if task.get("requires_confirmation"):
                    continue
                
                # Check dependencies
                deps_satisfied = True
                for dep_id in task.get("depends_on", []):
                    if dep_id not in completed_tasks:
                        deps_satisfied = False
                        break
                    dep_res = completed_tasks[dep_id]
                    if dep_res.status != "success":
                        deps_satisfied = False
                        break
                
                if deps_satisfied:
                    ready_tasks.append(task)
            
            if not ready_tasks:
                break
            
            # Resolve references
            for task in ready_tasks:
                task["arguments"] = self._resolve_refs(task["arguments"], completed_tasks)
            
            # Execute tasks
            async def run_task(t: SubTask):
                result = await self.executor.execute(t["tool_name"], t["arguments"], session_id=state["session_id"])
                return t["id"], result
            
            import asyncio
            results = await asyncio.gather(*[run_task(t) for t in ready_tasks])
            
            for task_id, result in results:
                completed_tasks[task_id] = result
                tool_results.append(result.model_dump())
                
                resolved_args = next(t["arguments"] for t in ready_tasks if t["id"] == task_id)
                tool_calls.append(
                    ChatToolCallTrace(
                        tool_name=result.tool_name,
                        arguments=resolved_args,
                        status=result.status,
                        error=result.error
                    )
                )
                
        # Resolve references for skipped write tools
        for task in plan:
            if task.get("requires_confirmation") and task["id"] not in completed_tasks:
                task["arguments"] = self._resolve_refs(task["arguments"], completed_tasks)
                
        return {
            "execution_plan": plan,
            "tool_results": tool_results,
            "tool_calls": tool_calls
        }

    @staticmethod
    def _deep_get(data: Any, path: str) -> Any:
        """Navigate nested dicts/lists using dot-notation; integer segments are list indices."""
        if data is None:
            return None
        head, _, tail = path.partition(".")
        try:
            idx = int(head)
            val = data[idx] if isinstance(data, list) and 0 <= idx < len(data) else None
        except ValueError:
            val = data.get(head) if isinstance(data, dict) else None
        return ChatSupervisor._deep_get(val, tail) if tail else val

    def _resolve_refs(self, args: Any, completed_tasks: dict[str, Any]) -> Any:
        if isinstance(args, dict):
            return {k: self._resolve_refs(v, completed_tasks) for k, v in args.items()}
        elif isinstance(args, list):
            return [self._resolve_refs(v, completed_tasks) for v in args]
        elif isinstance(args, str):
            if args.startswith("$"):
                parts = args[1:].split(".", 1)
                ref_id = parts[0]
                if ref_id in completed_tasks:
                    task_res = completed_tasks[ref_id]
                    data = task_res.data
                    if len(parts) > 1:
                        return self._deep_get(data, parts[1])
                    return data
            elif args.startswith("{{") and args.endswith("}}"):
                expr = args[2:-2].strip()
                parts = expr.split(".", 1)
                ref_id = parts[0]
                if ref_id in completed_tasks:
                    task_res = completed_tasks[ref_id]
                    data = task_res.data
                    if len(parts) > 1:
                        return self._deep_get(data, parts[1])
                    return data
        return args

    async def _synthesis_node(self, state: AgentState) -> dict[str, Any]:
        plan = state["execution_plan"]
        tool_results = state["tool_results"]
        tool_calls = state["tool_calls"]
        
        # 1. Check for pending write confirmations
        if plan:
            for task in plan:
                if task.get("requires_confirmation"):
                    confirmation_resp = self._build_confirmation_response(task)
                    return {"response": confirmation_resp}

        # 2. Check if we already have a response (e.g. from planner direct_response)
        if plan is not None and len(plan) == 0:
            if state["response"]:
                return {}

        # 3. Check if single tool with legacy formatter
        if plan and len(plan) == 1 and not plan[0].get("requires_confirmation"):
            task = plan[0]
            result_dict = next((res for res in tool_results if res["tool_name"] == task["tool_name"]), None)
            if result_dict:
                status = result_dict.get("status")
                data = result_dict.get("data") or {}
                error = result_dict.get("error")
                
                if status == "success":
                    answer = None
                    intent = ChatIntent.UNKNOWN

                    # Reactive clarification: a planning tool ran but is missing blocking data
                    # (e.g. income / budget limits). Ask the user instead of returning a
                    # guessed, unusable answer.
                    missing_resp = self._clarification_for_missing_data(
                        task["tool_name"], data if isinstance(data, dict) else {}, state["message"]
                    )
                    if missing_resp is not None:
                        missing_resp.tool_calls = tool_calls
                        return {"response": missing_resp}

                    if task["tool_name"] == "get_financial_health_score":
                        answer = self._format_financial_health_answer(data)
                        intent = ChatIntent.FINANCIAL_HEALTH_SCORE
                    elif task["tool_name"] == "get_anomalies":
                        answer = self._format_anomaly_answer(data)
                        intent = ChatIntent.ANOMALY_EXPLANATION
                    elif task["tool_name"] == "get_balance_forecast":
                        if self._is_current_balance_question(self._fold(state["message"])):
                            answer = self._format_current_balance_answer(data)
                        else:
                            answer = self._format_forecast_answer(data)
                        intent = ChatIntent.FORECAST_BALANCE
                    elif task["tool_name"] == "explain_budget_overrun":
                        answer = self._format_budget_overrun_explanation(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "simulate_purchase_impact":
                        answer = self._format_purchase_impact_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "get_emergency_fund_status":
                        answer = self._format_emergency_fund_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "get_debt_summary":
                        answer = self._format_debt_summary_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "get_recurring_transactions":
                        answer = self._format_recurring_answer(data)
                        intent = ChatIntent.SPENDING_BREAKDOWN
                    elif task["tool_name"] == "compare_period_spending":
                        answer = self._format_period_comparison_answer(data)
                        intent = ChatIntent.SPENDING_BREAKDOWN
                    elif task["tool_name"] == "get_cashflow_calendar":
                        answer = self._format_cashflow_calendar_answer(data)
                        intent = ChatIntent.FORECAST_BALANCE
                    elif task["tool_name"] == "get_account_summary":
                        answer = self._format_account_summary_answer(data)
                        intent = ChatIntent.SPENDING_BREAKDOWN
                    elif task["tool_name"] in ("compare_budget_vs_actual", "get_budget_status"):
                        answer = self._format_budget_status_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "recommend_budget_plan":
                        answer = self._format_budget_recommendation_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                        if isinstance(data, dict):
                            budgets = [
                                {"category": item.get("category"), "limit": item.get("recommended_budget")}
                                for item in list(data.get("recommended_budgets") or [])[:20]
                            ]
                            self._set_last_budget_plan(budgets)
                    elif task["tool_name"] == "get_savings_goals":
                        answer = self._format_savings_goals_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "simulate_savings_adjustment":
                        answer = self._format_savings_simulation_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                    elif task["tool_name"] == "plan_savings_goal":
                        answer = self._format_savings_plan_answer(data)
                        intent = ChatIntent.SAVING_SUGGESTION
                        self._set_last_savings_plan(dict(task["arguments"]))

                    if answer:
                        resp = ChatResponse(
                            answer=answer,
                            intent=intent,
                            tool_calls=tool_calls,
                            debug={"model": "fast_path"} if state["debug"] else None
                        )
                        return {"response": resp}
                else:
                    # Defensive clarification: the tool was rejected because a required
                    # argument was missing. Ask the user for it in plain language instead of
                    # surfacing the raw schema validation error.
                    field = self._missing_required_field(error)
                    if status == "rejected" and field:
                        resp = self._build_clarification_response(
                            f"Mình cần thêm thông tin để trả lời: bạn cho mình biết **{field}** nhé."
                        )
                        resp.tool_calls = tool_calls
                        return {"response": resp}
                    resp = ChatResponse(
                        answer=f"Minh chua thuc hien duoc. Loi: {error or 'Unknown error'}",
                        intent=ChatIntent.UNKNOWN,
                        tool_calls=tool_calls
                    )
                    return {"response": resp}

        # 4. LLM Synthesis
        api_key = self.settings.openai_api_key
        if not api_key:
            raise MissingOpenAIKeyError("OPENAI_API_KEY is missing")

        client = self._make_openai_client(api_key, timeout=30.0)
        model = self.settings.openai_model or _SAFE_DEFAULT_MODEL

        # Keep synthesis prompt minimal — no supervisor/planner instructions that tell
        # the model to select or call tools. The tools have already been executed; the
        # only job here is to write the answer from the returned data.
        system_content = (
            "You are a Vietnamese personal finance answer writer.\n"
            "The tools have ALREADY been executed. Their results are provided in the user message.\n"
            "DO NOT suggest calling more tools. DO NOT say 'I will check' or 'let me look'. "
            "ONLY write the final answer directly from the tool results.\n\n"
            "SYNTHESIS RULES:\n"
            "- The user question may contain MULTIPLE sub-questions. Answer EACH sub-question "
            "in the same order the user asked, as a clear separate sentence or bullet.\n"
            "- Use ONLY facts present in the tool results. Do NOT invent or estimate any number, "
            "balance, percentage, or date that is not in the tool results.\n"
            "- You MAY compute simple derived values from numbers in the tool results "
            "(e.g. savings_rate = (total_income - total_spent) / total_income, "
            "category_share = by_category[X] / total_spent). "
            "Label any derived value so the user knows it is calculated.\n"
            "- If a sub-question has no supporting tool result, say briefly that part is not "
            "available yet instead of guessing.\n"
            "- For forecast or savings figures, note they are estimates ('uoc tinh').\n"
            "- Respond in natural Vietnamese."
        )
        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    f"Câu hỏi của người dùng: {state['message']}\n\n"
                    f"Kết quả công cụ đã thực thi:\n{json.dumps(tool_results, ensure_ascii=False)}"
                ),
            },
        ]

        from spectra.chat.tracing import trace_span
        with trace_span("openai_synthesis", "llm", {"model": model, "messages_count": len(messages)}) as span_rec:
            final_res = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
            answer = final_res.choices[0].message.content or "Xin loi, minh chua the tao cau tra loi."
            span_rec.outputs = {"answer": answer}

        intent = self._infer_intent(state["message"], tool_calls)
        resp = ChatResponse(
            answer=answer,
            intent=intent,
            tool_calls=tool_calls,
            debug={"model": model} if state["debug"] else None
        )
        return {"response": resp, "synthesized_by_llm": True}

    def _build_confirmation_response(self, task: SubTask) -> ChatResponse:
        tool_name = task["tool_name"]
        arguments = task["arguments"]
        user_id = self.user_id

        if tool_name == "update_transaction_category":
            tx_id = arguments.get("tx_id", "")
            category = arguments.get("category", "")
            apply_to_future = bool(arguments.get("apply_to_future", False))
            txs = self.executor._get_transactions({"per_page": 20}).get("transactions", [])
            tx = next((t for t in txs if str(t.get("id")) == str(tx_id)), {})
            merchant = tx.get("merchant", "giao dịch")
            amount = abs(float(tx.get("amount", 0)))
            future_note = " (và áp dụng cho các giao dịch tương tự sau này)" if apply_to_future else ""
            action = pending_actions.create(
                user_id=user_id,
                action_type="update_transaction_category",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Đổi '{merchant}' sang {category}",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ chuyển giao dịch **{merchant}** ({amount:,.0f} VND) "
                    f"sang nhóm **{category}**{future_note}. Bạn xác nhận không?"
                ),
            )

        elif tool_name == "create_category_rule":
            pattern = arguments.get("pattern", "")
            category = arguments.get("category", "")
            rule_type = arguments.get("rule_type", "contains")
            rule_desc = "khớp regex" if rule_type == "regex" else "chứa từ"
            action = pending_actions.create(
                user_id=user_id,
                action_type="create_category_rule",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Quy tắc '{pattern}' → {category}",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ tạo quy tắc: giao dịch nào {rule_desc} **'{pattern}'** "
                    f"→ tự động xếp vào **{category}**. Bạn xác nhận không?"
                ),
            )

        elif tool_name == "create_savings_goal":
            name = arguments.get("name", "")
            target_amount = float(arguments.get("target_amount") or 0)
            target_date = arguments.get("target_date", "")
            current_amount = float(arguments.get("current_amount") or 0)
            current_note = f", đã có sẵn {current_amount:,.0f} VND" if current_amount > 0 else ""
            action = pending_actions.create(
                user_id=user_id,
                action_type="create_savings_goal",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Tạo mục tiêu '{name}'",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ tạo mục tiêu **'{name}'** — cần tiết kiệm "
                    f"**{target_amount:,.0f} VND** trước ngày **{target_date}**{current_note}. "
                    f"Bạn xác nhận không?"
                ),
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        elif tool_name == "update_savings_goal":
            goal_name = arguments.get("goal_name", "")
            changes = []
            if arguments.get("name"):
                changes.append(f"tên → '{arguments['name']}'")
            if arguments.get("target_amount") is not None:
                changes.append(f"mục tiêu → {float(arguments['target_amount']):,.0f} VND")
            if arguments.get("current_amount") is not None:
                changes.append(f"đã tiết kiệm → {float(arguments['current_amount']):,.0f} VND")
            if arguments.get("target_date"):
                changes.append(f"hạn → {arguments['target_date']}")
            if arguments.get("status"):
                status_map = {"active": "đang chạy", "paused": "tạm dừng", "completed": "hoàn thành", "archived": "lưu trữ"}
                changes.append(f"trạng thái → {status_map.get(arguments['status'], arguments['status'])}")
            change_str = ", ".join(changes) if changes else "thông tin mới"
            label = f"'{goal_name}'" if goal_name else "mục tiêu tiết kiệm"
            action = pending_actions.create(
                user_id=user_id,
                action_type=tool_name,
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Cập nhật {label}",
            )
            return self._confirmation_response(
                action,
                answer=f"Mình sẽ cập nhật {label}: {change_str}. Bạn xác nhận không?",
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        elif tool_name == "archive_savings_goal":
            goal_name = arguments.get("goal_name", "")
            label = f"**'{goal_name}'**" if goal_name else "mục tiêu tiết kiệm này"
            action = pending_actions.create(
                user_id=user_id,
                action_type=tool_name,
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Hủy {goal_name or 'mục tiêu tiết kiệm'}",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ hủy (lưu trữ) {label}. "
                    f"Mục tiêu sẽ không còn hoạt động và không tính vào kế hoạch ngân sách. "
                    f"Bạn xác nhận không?"
                ),
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        elif tool_name == "update_budget_limit":
            category = arguments.get("category", "")
            limit = float(arguments.get("limit") or 0)
            action = pending_actions.create(
                user_id=user_id,
                action_type="update_budget_limit",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Ngân sách {category} → {limit:,.0f} VND",
            )
            return self._confirmation_response(
                action,
                answer=f"Mình sẽ đặt ngân sách **{category}** thành **{limit:,.0f} VND/tháng**. Bạn xác nhận không?",
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        elif tool_name == "upsert_budget_plan":
            budgets: list[dict] = arguments.get("budgets") or []
            lines = [f"• {b.get('category', '?')}: {float(b.get('limit', 0)):,.0f} VND" for b in budgets[:8]]
            budget_list = "\n" + "\n".join(lines) + ("\n• ..." if len(budgets) > 8 else "")
            action = pending_actions.create(
                user_id=user_id,
                action_type="upsert_budget_plan",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Áp dụng kế hoạch ngân sách ({len(budgets)} danh mục)",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ áp dụng kế hoạch ngân sách gồm **{len(budgets)} danh mục**:{budget_list}\n"
                    f"Bạn xác nhận không?"
                ),
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        elif tool_name == "remember_user_preference":
            key = arguments.get("key", "")
            value = arguments.get("value", {})
            reason = arguments.get("reason", "")
            value_str = str(value) if not isinstance(value, dict) else ", ".join(f"{k}={v}" for k, v in value.items())
            action = pending_actions.create(
                user_id=user_id,
                action_type="remember_user_preference",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Ghi nhớ '{key}'",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ ghi nhớ **{key}**: {value_str}"
                    + (f" (lý do: {reason})" if reason else "")
                    + ". Bạn đồng ý để mình nhớ điều này cho các lần trò chuyện sau không?"
                ),
                intent=ChatIntent.PRIVACY_OR_PERMISSION,
            )

        elif tool_name == "forget_user_memory":
            memory_id = arguments.get("memory_id", "")
            action = pending_actions.create(
                user_id=user_id,
                action_type="forget_user_memory",
                tool_name=tool_name,
                tool_arguments=arguments,
                human_summary=f"Xóa ghi nhớ {memory_id}",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Mình sẽ xóa ghi nhớ này (ID: `{memory_id}`). "
                    f"Hành động không thể hoàn tác. Bạn xác nhận không?"
                ),
                intent=ChatIntent.PRIVACY_OR_PERMISSION,
            )

        action = pending_actions.create(
            user_id=user_id,
            action_type=tool_name,
            tool_name=tool_name,
            tool_arguments=arguments,
            human_summary=f"Thực hiện {tool_name}",
        )
        return self._confirmation_response(
            action,
            answer=f"Mình cần bạn xác nhận để thực hiện '{tool_name}'. Bạn đồng ý không?",
        )

    async def _finalizer_node(self, state: AgentState) -> dict[str, Any]:
        resp = state["response"]
        if not resp:
            return {}
            
        tool_results_list = state["tool_results"]
        req = ChatRequest(
            message=state["message"],
            session_id=state["session_id"],
            scope=state["scope"],
            debug=state["debug"]
        )
        
        finalized = await self._finalize_read_answer(req, resp, tool_results=tool_results_list)
        return {"response": finalized}

    async def _output_guard_node(self, state: AgentState) -> dict[str, Any]:
        resp = state["response"]
        if not resp:
            return {}
        from spectra.chat.guardrails.engine import guardrail_engine
        resp.answer = guardrail_engine.check_output(resp.answer, resp.intent.value)
        return {"response": resp}

    @staticmethod
    def _make_openai_client(api_key: str, *, timeout: float = 30.0) -> Any:
        from openai import OpenAI

        return OpenAI(api_key=api_key, timeout=timeout)

    async def _finalize_read_answer(
        self,
        chat_request: ChatRequest,
        response: ChatResponse,
        *,
        tool_results: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        if response.requires_confirmation or not response.tool_calls:
            return response
        if any(trace.status != "success" for trace in response.tool_calls):
            return self._with_finalizer_debug(chat_request, response, used=False, fallback_reason="tool_not_success")
        if not str(response.answer or "").strip():
            return self._with_finalizer_debug(chat_request, response, used=False, fallback_reason="empty_fallback")
        if not self.settings.chat_finalizer_enabled:
            return self._with_finalizer_debug(chat_request, response, used=False, fallback_reason="disabled")
        api_key = self.settings.openai_api_key
        if not api_key:
            return self._with_finalizer_debug(chat_request, response, used=False, fallback_reason="missing_openai_key")

        model = self.settings.openai_model or _SAFE_DEFAULT_MODEL
        payload = redact_payload(
            {
                "user_message": redact_text(chat_request.message),
                "intent": response.intent.value,
                "fallback_answer": redact_text(response.answer),
                "tool_calls": [trace.model_dump(mode="json") for trace in response.tool_calls],
                "tool_results": tool_results or [],
            }
        )
        messages = [
            {"role": "system", "content": FINALIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Rewrite the final answer from this JSON payload. "
                    "Preserve the facts and do not add facts.\n\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ]

        try:
            from spectra.chat.tracing import trace_span

            client = self._make_openai_client(api_key, timeout=20.0)
            with trace_span("openai_finalizer", "llm", {"model": model, "messages_count": len(messages)}) as span_rec:
                final = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
                answer = str(final.choices[0].message.content or "").strip()
                span_rec.outputs = {"answer": answer}
        except Exception:
            logger.debug("Chat finalizer failed", exc_info=True)
            return self._with_finalizer_debug(chat_request, response, used=False, fallback_reason="openai_error")

        if not self._is_safe_finalizer_answer(answer):
            return self._with_finalizer_debug(chat_request, response, used=False, fallback_reason="unsafe_output")

        finalized = response.model_copy(update={"answer": answer})
        return self._with_finalizer_debug(chat_request, finalized, used=True, model=model)

    @staticmethod
    def _is_safe_finalizer_answer(answer: str) -> bool:
        text = str(answer or "").strip()
        if not text or len(text) > _FINALIZER_MAX_CHARS:
            return False
        if _FINALIZER_BLOCKED_RE.search(text):
            return False
        if _FINALIZER_TOOL_NAME_RE.search(text):
            return False
        if _RAW_LONG_IDENTIFIER_RE.search(text):
            return False
        if _UUID_IN_TEXT_RE.search(text):
            return False
        return True

    @staticmethod
    def _with_finalizer_debug(
        chat_request: ChatRequest,
        response: ChatResponse,
        *,
        used: bool,
        fallback_reason: str | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        if not chat_request.debug:
            return response
        finalizer_debug: dict[str, Any] = {"used": used}
        if fallback_reason:
            finalizer_debug["fallback_reason"] = fallback_reason
        if model:
            finalizer_debug["model"] = model
        debug = dict(response.debug or {})
        debug["finalizer"] = finalizer_debug
        return response.model_copy(update={"debug": debug})

    async def _handle_confirmation_request(self, chat_request: ChatRequest) -> ChatResponse | None:
        if not chat_request.confirmation_id or chat_request.confirm is None:
            return None
        if not chat_request.confirm:
            ok, _message = pending_actions.cancel(chat_request.confirmation_id, user_id=self.user_id)
            return ChatResponse(
                answer="Minh da huy yeu cau nay." if ok else "Minh khong tim thay yeu cau can huy.",
                intent=ChatIntent.CATEGORY_CORRECTION,
            )

        action = pending_actions.get(chat_request.confirmation_id)
        if not action:
            return ChatResponse(
                answer="Ma xac nhan nay khong ton tai hoac da het han. Ban vui long gui lai yeu cau.",
                intent=ChatIntent.CATEGORY_CORRECTION,
            )
        if action.user_id != self.user_id:
            return ChatResponse(
                answer="Ma xac nhan nay khong thuoc phien cua ban nen minh khong the thuc hien.",
                intent=ChatIntent.PRIVACY_OR_PERMISSION,
            )
        if action.status != "pending":
            return ChatResponse(
                answer="Yeu cau nay khong con cho xac nhan nen minh khong thuc hien lai.",
                intent=ChatIntent.CATEGORY_CORRECTION,
            )

        result = await self.executor.execute(
            action.tool_name,
            action.tool_arguments,
            confirmation_id=action.confirmation_id,
            session_id=chat_request.session_id,
        )
        trace = ChatToolCallTrace(
            tool_name=action.tool_name,
            arguments=action.tool_arguments,
            status=result.status,
            error=result.error,
        )
        if result.status != "success":
            return ChatResponse(
                answer="Minh chua thuc hien duoc thay doi nay. Vui long thu lai sau.",
                intent=ChatIntent.CATEGORY_CORRECTION,
                tool_calls=[trace],
            )

        if action.tool_name == "update_transaction_category":
            data = result.data if isinstance(result.data, dict) else {}
            merchant = str(data.get("merchant") or "")
            category = str(data.get("category") or action.tool_arguments.get("category") or "")
            _LAST_CATEGORY_CORRECTIONS[self.user_id] = {"pattern": merchant, "category": category}
            return ChatResponse(
                answer=(
                    f"Minh da doi giao dich {merchant} sang nhom {category}.\n\n"
                    f"Ban co muon minh ghi nho rang cac giao dich chua '{merchant}' se duoc goi y vao nhom {category} cho lan sau khong?"
                ),
                intent=ChatIntent.CATEGORY_CORRECTION,
                tool_calls=[trace],
                suggested_actions=[
                    SuggestedAction(type="confirm", action="remember_category_rule", label="Ghi nho rule"),
                    SuggestedAction(type="cancel", action="skip_memory", label="Bo qua"),
                ],
            )

        if action.tool_name == "create_savings_goal":
            data = result.data if isinstance(result.data, dict) else {}
            goal = data.get("goal") if isinstance(data.get("goal"), dict) else {}
            amount = float(goal.get("target_amount") or action.tool_arguments.get("target_amount") or 0)
            monthly = float((data.get("plan") or {}).get("required_plan", {}).get("required_monthly_saving") or 0)
            return ChatResponse(
                answer=(
                    f"Minh da tao muc tieu tiet kiem {amount:,.0f} VND. "
                    f"Ban can tiet kiem khoang {monthly:,.0f} VND/thang de dat muc tieu dung han."
                ),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        if action.tool_name in {"update_savings_goal", "archive_savings_goal"}:
            return ChatResponse(
                answer="Minh da cap nhat muc tieu tiet kiem cua ban.",
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        if action.tool_name == "update_budget_limit":
            category = str(action.tool_arguments.get("category") or "")
            limit = float(action.tool_arguments.get("limit") or 0)
            return ChatResponse(
                answer=f"Minh da cap nhat ngan sach {category} thanh {limit:,.0f} VND.",
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        if action.tool_name == "upsert_budget_plan":
            return ChatResponse(
                answer="Minh da ap dung ke hoach ngan sach ban xac nhan.",
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        if action.tool_name == "remember_user_preference":
            return ChatResponse(
                answer="Minh da ghi nho so thich nay cho cac lan tro chuyen sau.",
                intent=ChatIntent.PRIVACY_OR_PERMISSION,
                tool_calls=[trace],
                memory_updates=[{"status": "saved", "memory_type": action.tool_arguments.get("memory_type", "preference")}],
            )

        if action.tool_name == "forget_user_memory":
            return ChatResponse(
                answer="Minh da xoa ghi nho nay.",
                intent=ChatIntent.PRIVACY_OR_PERMISSION,
                tool_calls=[trace],
                memory_updates=[{"status": "deleted", "memory_id": action.tool_arguments.get("memory_id")}],
            )

        return ChatResponse(
            answer="Minh da ghi nho rule category nay cho cac giao dich sau.",
            intent=ChatIntent.CATEGORY_CORRECTION,
            tool_calls=[trace],
        )

    async def _handle_phase4_read_flow(self, chat_request: ChatRequest) -> ChatResponse | None:
        normalized = self._fold(chat_request.message)
        insight_flow = await self._handle_phase8_insight_flow(chat_request, normalized)
        if insight_flow:
            return insight_flow

        budget_flow = await self._handle_phase7_budget_flow(chat_request, normalized)
        if budget_flow:
            return budget_flow

        goal_flow = await self._handle_phase6_savings_goal_flow(chat_request, normalized)
        if goal_flow:
            return goal_flow

        summary_flow = await self._handle_summary_flow(chat_request, normalized)
        if summary_flow:
            return summary_flow

        if self._is_financial_health_question(normalized):
            arguments = {"scope": chat_request.scope, "refresh": False}
            result = await self.executor.execute("get_financial_health_score", arguments)
            trace = ChatToolCallTrace(
                tool_name="get_financial_health_score",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            response = ChatResponse(
                answer=self._format_financial_health_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.FINANCIAL_HEALTH_SCORE,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_anomaly_question(normalized):
            arguments = {"limit": 10, "scope": "cycle"}
            result = await self.executor.execute("get_anomalies", arguments)
            trace = ChatToolCallTrace(
                tool_name="get_anomalies",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            response = ChatResponse(
                answer=self._format_anomaly_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.ANOMALY_EXPLANATION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_current_balance_question(normalized) or self._is_forecast_question(normalized):
            arguments = {"scope": "current_month"}
            result = await self.executor.execute("get_balance_forecast", arguments)
            trace = ChatToolCallTrace(
                tool_name="get_balance_forecast",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            data = result.data if isinstance(result.data, dict) else {}
            answer = (
                self._format_current_balance_answer(data)
                if self._is_current_balance_question(normalized)
                else self._format_forecast_answer(data)
            )
            response = ChatResponse(
                answer=answer,
                intent=ChatIntent.FORECAST_BALANCE,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])
        return None

    async def _handle_phase8_insight_flow(self, chat_request: ChatRequest, normalized: str) -> ChatResponse | None:
        if self._is_budget_overrun_explanation_question(normalized):
            arguments = {"scope": chat_request.scope, "category": self._parse_budget_overrun_category(normalized)}
            result = await self.executor.execute("explain_budget_overrun", arguments)
            trace = ChatToolCallTrace(tool_name="explain_budget_overrun", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_budget_overrun_explanation(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        purchase = self._parse_purchase_simulation_request(chat_request.message)
        if purchase:
            arguments = {"scope": chat_request.scope, **purchase}
            result = await self.executor.execute("simulate_purchase_impact", arguments)
            trace = ChatToolCallTrace(tool_name="simulate_purchase_impact", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_purchase_impact_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_emergency_fund_question(normalized):
            arguments = {"months_target": self._parse_months_target(normalized) or 3}
            result = await self.executor.execute("get_emergency_fund_status", arguments)
            trace = ChatToolCallTrace(tool_name="get_emergency_fund_status", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_emergency_fund_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_debt_question(normalized):
            arguments = {"scope": chat_request.scope}
            result = await self.executor.execute("get_debt_summary", arguments)
            trace = ChatToolCallTrace(tool_name="get_debt_summary", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_debt_summary_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        # "lời khuyên để cắt giảm [category]" must be caught BEFORE recurring check
        # because "hàng tháng" in the message triggers _is_recurring_question as a false positive.
        if self._is_category_advice_question(normalized):
            category = self._parse_advice_category(normalized)
            arguments = {"scope": chat_request.scope}
            if category:
                arguments["category"] = category
            result = await self.executor.execute("explain_budget_overrun", arguments)
            trace = ChatToolCallTrace(tool_name="explain_budget_overrun", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_budget_overrun_explanation(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_recurring_question(normalized):
            arguments = {"scope": chat_request.scope, "limit": 10}
            result = await self.executor.execute("get_recurring_transactions", arguments)
            trace = ChatToolCallTrace(tool_name="get_recurring_transactions", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_recurring_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SPENDING_BREAKDOWN,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_period_comparison_question(normalized):
            arguments: dict[str, Any] = {}
            result = await self.executor.execute("compare_period_spending", arguments)
            trace = ChatToolCallTrace(tool_name="compare_period_spending", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_period_comparison_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SPENDING_BREAKDOWN,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_cashflow_calendar_question(normalized):
            arguments = {"days": 30}
            result = await self.executor.execute("get_cashflow_calendar", arguments)
            trace = ChatToolCallTrace(tool_name="get_cashflow_calendar", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_cashflow_calendar_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.FORECAST_BALANCE,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])
        return None

    async def _handle_summary_flow(self, chat_request: ChatRequest, normalized: str) -> ChatResponse | None:
        # Average monthly spending over the last N months, e.g. "trung bình chi tiêu 6 tháng gần đây".
        # Routed deterministically so the planner does not improvise a wrong comparison with
        # overlapping date ranges.
        recent_months = self._parse_recent_months(normalized)
        if recent_months and self._is_average_question(normalized):
            window = self._recent_months_window(recent_months)
            arguments = {"scope": chat_request.scope, **window}
            result = await self.executor.execute("get_account_summary", arguments)
            trace = ChatToolCallTrace(
                tool_name="get_account_summary",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            response = ChatResponse(
                answer=self._format_average_spending_answer(
                    result.data if isinstance(result.data, dict) else {}, recent_months
                ),
                intent=ChatIntent.SPENDING_BREAKDOWN,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if any(token in normalized for token in ["so voi", "so sanh", "nhieu hon", "it hon"]):
            return None
        months = re.findall(r"\bthang\s+(\d{1,2})\b", normalized)
        if len(months) > 1:
            return None

        period = self._parse_summary_period(chat_request.message)
        if not period or not self._is_summary_question(normalized):
            return None

        arguments = {"scope": chat_request.scope, **period}
        result = await self.executor.execute("get_account_summary", arguments)
        trace = ChatToolCallTrace(
            tool_name="get_account_summary",
            arguments=arguments,
            status=result.status,
            error=result.error,
        )
        response = ChatResponse(
            answer=self._format_account_summary_answer(result.data if isinstance(result.data, dict) else {}),
            intent=ChatIntent.SPENDING_BREAKDOWN,
            tool_calls=[trace],
        )
        return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

    async def _handle_phase7_budget_flow(self, chat_request: ChatRequest, normalized: str) -> ChatResponse | None:
        is_pct_reduction = self._is_pct_spending_reduction_question(normalized)
        if "ngan sach" not in normalized and not self._is_budget_apply_request(normalized) and not is_pct_reduction:
            return None

        # B2: "giảm chi tiêu X%" → get budget data so user knows what to cut
        if is_pct_reduction and "ngan sach" not in normalized:
            arguments: dict[str, Any] = {"scope": chat_request.scope}
            result = await self.executor.execute("get_budget_status", arguments)
            trace = ChatToolCallTrace(tool_name="get_budget_status", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_budget_status_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if self._is_budget_apply_request(normalized):
            budgets = self._get_last_budget_plan()
            if not budgets:
                return ChatResponse(
                    answer="Minh chua co ke hoach ngan sach nao de ap dung. Ban hay yeu cau minh de xuat ngan sach truoc.",
                    intent=ChatIntent.SAVING_SUGGESTION,
                )
            action = pending_actions.create(
                user_id=self.user_id,
                action_type="upsert_budget_plan",
                tool_name="upsert_budget_plan",
                tool_arguments={"budgets": budgets},
                human_summary="Ap dung ke hoach ngan sach de xuat",
            )
            return self._confirmation_response(
                action,
                answer="Minh se ap dung ke hoach ngan sach da de xuat. Ban xac nhan cap nhat khong?",
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        parsed_update = self._parse_budget_limit_request(chat_request.message)
        if parsed_update and self._is_budget_update_request(normalized):
            action = pending_actions.create(
                user_id=self.user_id,
                action_type="update_budget_limit",
                tool_name="update_budget_limit",
                tool_arguments=parsed_update,
                human_summary=f"Cap nhat ngan sach {parsed_update['category']} -> {parsed_update['limit']:,.0f} VND",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Minh se doi ngan sach {parsed_update['category']} thanh {parsed_update['limit']:,.0f} VND. "
                    "Ban xac nhan cap nhat khong?"
                ),
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        # D5: "lên kế hoạch ngân sách" must be checked BEFORE parsed_sim because parse_budget_limit_request
        # may spuriously match percentage digits in the message (e.g. "30%") and "neu" fires the sim branch.
        if any(token in normalized for token in ["nen dat", "chia ngan sach", "tao ngan sach", "hop ly", "dieu chinh ngan sach", "len ke hoach", "lap ke hoach", "ke hoach ngan sach"]):
            arguments = {"scope": chat_request.scope}
            result = await self.executor.execute("recommend_budget_plan", arguments)
            trace = ChatToolCallTrace(tool_name="recommend_budget_plan", arguments=arguments, status=result.status, error=result.error)
            data = result.data if isinstance(result.data, dict) else {}
            if result.status == "success":
                budgets = [
                    {"category": item.get("category"), "limit": item.get("recommended_budget")}
                    for item in list(data.get("recommended_budgets") or [])[:20]
                ]
                self._set_last_budget_plan(budgets)
            response = ChatResponse(
                answer=self._format_budget_recommendation_answer(data),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        parsed_sim = self._parse_budget_limit_request(chat_request.message)
        if parsed_sim and any(token in normalized for token in ["neu", "thi co", "dat muc"]):
            arguments = {"scope": chat_request.scope, "adjustments": [parsed_sim]}
            result = await self.executor.execute("simulate_budget_adjustment", arguments)
            trace = ChatToolCallTrace(tool_name="simulate_budget_adjustment", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_budget_simulation_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        if any(token in normalized for token in ["vuot ngan sach", "dang vuot", "danh muc nao", "so sanh"]):
            tool = "compare_budget_vs_actual" if "so sanh" in normalized else "get_budget_status"
            arguments = {"scope": chat_request.scope}
            result = await self.executor.execute(tool, arguments)
            trace = ChatToolCallTrace(tool_name=tool, arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_budget_status_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        return None

    async def _handle_phase6_savings_goal_flow(self, chat_request: ChatRequest, normalized: str) -> ChatResponse | None:
        if self._is_goal_create_request(normalized):
            plan_args = self._get_last_savings_plan() or self._parse_savings_goal(chat_request.message)
            if not plan_args:
                return ChatResponse(
                    answer="Ban cho minh muc tieu can tiet kiem va thoi han nhe, vi du: tiet kiem 20 trieu trong 6 thang.",
                    intent=ChatIntent.SAVING_SUGGESTION,
                )
            action = pending_actions.create(
                user_id=self.user_id,
                action_type="create_savings_goal",
                tool_name="create_savings_goal",
                tool_arguments=plan_args,
                human_summary=f"Tao muc tieu {plan_args.get('name')}",
            )
            return self._confirmation_response(
                action,
                answer=(
                    f"Minh se tao muc tieu '{plan_args.get('name')}'. "
                    "Ban xac nhan muon tao muc tieu nay khong?"
                ),
                intent=ChatIntent.SAVING_SUGGESTION,
            )

        if self._is_goal_progress_question(normalized):
            arguments = {"status": "active"}
            result = await self.executor.execute("get_savings_goals", arguments)
            trace = ChatToolCallTrace(tool_name="get_savings_goals", arguments=arguments, status=result.status, error=result.error)
            response = ChatResponse(
                answer=self._format_savings_goals_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        simulation = self._parse_savings_simulation(chat_request.message)
        if simulation:
            base = self._get_last_savings_plan()
            if not base:
                return ChatResponse(
                    answer="Minh can biet muc tieu va thoi han truoc khi mo phong. Ban hay noi vi du: tiet kiem 20 trieu trong 6 thang.",
                    intent=ChatIntent.SAVING_SUGGESTION,
                )
            arguments = {
                "target_amount": base["target_amount"],
                "current_amount": base.get("current_amount", 0),
                "target_date": base["target_date"],
                "adjustments": [simulation],
                "currency": base.get("currency", "VND"),
            }
            result = await self.executor.execute("simulate_savings_adjustment", arguments)
            trace = ChatToolCallTrace(
                tool_name="simulate_savings_adjustment",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            response = ChatResponse(
                answer=self._format_savings_simulation_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])

        plan_args = self._parse_savings_goal(chat_request.message)
        if plan_args and self._is_goal_planning_question(normalized):
            result = await self.executor.execute("plan_savings_goal", plan_args)
            trace = ChatToolCallTrace(tool_name="plan_savings_goal", arguments=plan_args, status=result.status, error=result.error)
            if result.status == "success":
                self._set_last_savings_plan(dict(plan_args))
            response = ChatResponse(
                answer=self._format_savings_plan_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
            return await self._finalize_read_answer(chat_request, response, tool_results=[result.model_dump(mode="json")])
        return None

    def _handle_phase3_category_flow(self, chat_request: ChatRequest) -> ChatResponse | None:
        message = chat_request.message.strip()
        normalized = self._fold(message)
        if self._is_unsafe_bulk_or_reset(normalized):
            return ChatResponse(
                answer="Chuc nang nay se duoc them o phase sau. Hien tai minh co the giup ban xem tong quan chi tieu, xem giao dich, danh muc va sua category giao dich.",
                intent=ChatIntent.UNKNOWN,
            )

        selection = self._parse_candidate_selection(message)
        if selection is not None:
            return self._build_confirmation_from_candidate_selection(selection)

        correction = self._parse_category_correction(message)
        if correction:
            merchant, category = correction
            return self._build_category_correction_confirmation(merchant, category)

        memory = self._parse_memory_request(message)
        if memory:
            pattern, category = memory
            return self._build_rule_confirmation(pattern, category)

        if self._is_memory_affirmation(normalized):
            previous = _LAST_CATEGORY_CORRECTIONS.get(self.user_id)
            if previous:
                return self._build_rule_confirmation(str(previous["pattern"]), str(previous["category"]))
            preference = self._pending_preference_from_context()
            if preference:
                return self._build_preference_confirmation(preference)
        if self._is_memory_lookup_request(normalized):
            return self._build_memory_lookup_response()
        if self._is_forget_memory_request(normalized):
            return self._build_forget_memory_response(normalized)
        preference = self._parse_preference_memory_request(message)
        if preference:
            return self._build_preference_prompt(preference)
        return None

    def _build_category_correction_confirmation(self, merchant: str, category: str) -> ChatResponse:
        transactions = self.executor._get_transactions({"search": merchant, "per_page": 5}).get("transactions", [])
        if not transactions:
            return ChatResponse(
                answer=f"Minh chua tim thay giao dich nao khop voi '{merchant}'.",
                intent=ChatIntent.CATEGORY_CORRECTION,
            )
        if len(transactions) > 1:
            self._set_last_category_candidates({
                "category": category,
                "transactions": transactions[:5],
            })
            lines = ["Minh tim thay vai giao dich gan giong. Ban muon sua giao dich nao?"]
            for index, tx in enumerate(transactions[:5], start=1):
                lines.append(
                    f"{index}. {tx.get('date')} - {tx.get('merchant')} - {abs(float(tx.get('amount') or 0)):,.0f} VND - hien tai: {tx.get('category')}"
                )
            return ChatResponse(answer="\n".join(lines), intent=ChatIntent.CATEGORY_CORRECTION)

        tx = transactions[0]
        action = pending_actions.create(
            user_id=self.user_id,
            action_type="update_transaction_category",
            tool_name="update_transaction_category",
            tool_arguments={"tx_id": str(tx["id"]), "category": category, "apply_to_future": False},
            human_summary=f"Doi giao dich {tx.get('merchant')} sang {category}",
        )
        return self._confirmation_response(
            action,
            answer=(
                f"Minh tim thay giao dich {tx.get('merchant')} {abs(float(tx.get('amount') or 0)):,.0f} VND ngay {tx.get('date')}. "
                f"Ban co muon doi giao dich nay sang nhom {category} khong?"
            ),
        )

    def _build_confirmation_from_candidate_selection(self, selection: int) -> ChatResponse:
        pending_selection = self._get_last_category_candidates()
        if not pending_selection:
            return ChatResponse(
                answer="Minh chua co danh sach giao dich nao de chon. Ban vui long gui lai yeu cau sua category.",
                intent=ChatIntent.CATEGORY_CORRECTION,
            )
        transactions = list(pending_selection.get("transactions") or [])
        if selection < 1 or selection > len(transactions):
            return ChatResponse(
                answer=f"Lua chon {selection} khong nam trong danh sach. Ban vui long chon tu 1 den {len(transactions)}.",
                intent=ChatIntent.CATEGORY_CORRECTION,
            )
        tx = transactions[selection - 1]
        category = str(pending_selection.get("category") or "")
        action = pending_actions.create(
            user_id=self.user_id,
            action_type="update_transaction_category",
            tool_name="update_transaction_category",
            tool_arguments={"tx_id": str(tx["id"]), "category": category, "apply_to_future": False},
            human_summary=f"Doi giao dich {tx.get('merchant')} sang {category}",
        )
        return self._confirmation_response(
            action,
            answer=(
                f"Ban da chon giao dich {tx.get('merchant')} {abs(float(tx.get('amount') or 0)):,.0f} VND ngay {tx.get('date')}. "
                f"Ban co muon doi giao dich nay sang nhom {category} khong?"
            ),
        )

    def _build_rule_confirmation(self, pattern: str, category: str) -> ChatResponse:
        action = pending_actions.create(
            user_id=self.user_id,
            action_type="create_category_rule",
            tool_name="create_category_rule",
            tool_arguments={"rule_type": "contains", "pattern": pattern, "category": category},
            human_summary=f"Ghi nho rule {pattern} -> {category}",
        )
        return self._confirmation_response(
            action,
            answer=f"De tranh hoc sai, minh can ban xac nhan them: ghi nho rule '{pattern}' -> '{category}' cho cac giao dich sau nay nhe?",
        )

    def _build_preference_prompt(self, candidate: dict[str, Any]) -> ChatResponse:
        key = str(candidate.get("key") or "preference")
        value = candidate.get("value") if isinstance(candidate.get("value"), dict) else {}
        if self.session_id:
            self._set_session_state("conversation_summary", {"pending_preference": candidate})
        label = "cau tra loi ngan gon hon" if value.get("preference") == "shorter_answers" else "so thich nay"
        return ChatResponse(
            answer=f"Ban co muon minh ghi nho rang ban thich {label} khong?",
            intent=ChatIntent.PRIVACY_OR_PERMISSION,
            suggested_actions=[SuggestedAction(type="follow_up", action="follow_up", label="Co"), SuggestedAction(type="cancel", action="cancel", label="Khong")],
            memory_updates=[{"status": "pending_confirmation", "key": key}],
        )

    def _build_preference_confirmation(self, candidate: dict[str, Any]) -> ChatResponse:
        memory = upsert_user_memory(
            user_id=self.user_id,
            memory_type=str(candidate.get("memory_type") or "preference"),
            key=str(candidate.get("key") or "preference"),
            value=candidate.get("value") if isinstance(candidate.get("value"), dict) else {},
            source="chat_confirmed",
            confidence=1.0,
        )
        return ChatResponse(
            answer="Minh da ghi nho so thich nay cho cac lan tro chuyen sau.",
            intent=ChatIntent.PRIVACY_OR_PERMISSION,
            memory_updates=[{"status": "saved", "memory_id": memory.get("id"), "key": memory.get("key")}],
        )

    def _build_memory_lookup_response(self) -> ChatResponse:
        memories = list((self.chat_context.get("safe_user_memories") or [])[:10])
        if not memories:
            return ChatResponse(
                answer="Hien tai minh chua co ghi nho lau dai nao ve so thich cua ban.",
                intent=ChatIntent.PRIVACY_OR_PERMISSION,
            )
        lines = ["Minh dang ghi nho cac so thich an toan sau:"]
        for index, item in enumerate(memories, start=1):
            lines.append(f"{index}. {item.get('key')}: {item.get('value')}")
        return ChatResponse(answer="\n".join(lines), intent=ChatIntent.PRIVACY_OR_PERMISSION)

    def _build_forget_memory_response(self, normalized: str) -> ChatResponse:
        memories = list((self.chat_context.get("safe_user_memories") or [])[:20])
        if not memories:
            return ChatResponse(answer="Minh chua co ghi nho nao de xoa.", intent=ChatIntent.PRIVACY_OR_PERMISSION)
        target = None
        if "ngan gon" in normalized:
            target = next((item for item in memories if item.get("key") == "response_style"), None)
        target = target or memories[0]
        action = pending_actions.create(
            user_id=self.user_id,
            action_type="forget_user_memory",
            tool_name="forget_user_memory",
            tool_arguments={"memory_id": str(target.get("id") or "")},
            human_summary=f"Xoa ghi nho {target.get('key')}",
        )
        return self._confirmation_response(
            action,
            answer=f"Minh se xoa ghi nho '{target.get('key')}'. Ban xac nhan xoa khong?",
            intent=ChatIntent.PRIVACY_OR_PERMISSION,
        )

    @staticmethod
    def _confirmation_response(
        action: PendingAction,
        *,
        answer: str,
        intent: ChatIntent = ChatIntent.CATEGORY_CORRECTION,
    ) -> ChatResponse:
        return ChatResponse(
            answer=answer,
            intent=intent,
            requires_confirmation=True,
            confirmation=ChatConfirmation(
                confirmation_id=action.confirmation_id,
                action_type=action.action_type,
                summary=action.human_summary,
            ),
            suggested_actions=[
                SuggestedAction(
                    type="confirm",
                    action="confirm",
                    label="Dong y",
                    confirmation_id=action.confirmation_id,
                    arguments={"confirmation_id": action.confirmation_id, "confirm": True},
                ),
                SuggestedAction(type="cancel", action="cancel", label="Huy", confirmation_id=action.confirmation_id),
            ],
        )

    def _build_user_message(self, chat_request: ChatRequest) -> str:
        from datetime import date, timedelta

        today_vn = get_today_in_user_timezone()
        today_str = today_vn.isoformat()
        context = self._format_context_for_prompt()

        # Date-range examples below are computed from today so they always agree with
        # the rule text. Hardcoded example dates go stale and the planner copies them
        # literally (e.g. picking the wrong end-of-month day).
        tomorrow_str = (today_vn + timedelta(days=1)).isoformat()  # exclusive end for partial periods
        week_monday = today_vn - timedelta(days=today_vn.weekday())
        week_monday_str = week_monday.isoformat()
        last_week_monday_str = (week_monday - timedelta(days=7)).isoformat()
        month_start = today_vn.replace(day=1)
        month_start_str = month_start.isoformat()
        prev_month_start_str = (month_start - timedelta(days=1)).replace(day=1).isoformat()
        cur_quarter = (today_vn.month - 1) // 3 + 1
        quarter_start_str = date(today_vn.year, (cur_quarter - 1) * 3 + 1, 1).isoformat()
        weekday_vn = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật"][today_vn.weekday()]

        prompt_rules = f"""### Section A — TOOL SELECTION RULES
TOOL SELECTION RULES (ưu tiên cao nhất):

Dùng compare_period_spending khi user so sánh 2 kỳ thời gian với nhau:
- Từ tường minh (có kèm mốc thời gian): "so sánh tháng này với tháng trước", "đối chiếu Q1 và Q2"
- Từ ngầm định: "nhiều hơn không?", "ít hơn không?", "tăng chưa?", "giảm chưa?", "có thay đổi không?", "khác nhau thế nào?"
- Pattern: "[period A] vs [period B]", "[tháng/quý/năm A] với [tháng/quý/năm B]"

KHÔNG dùng compare_period_spending cho:
- "so sánh với người cùng tuổi/địa vị" → đây là peer comparison, Spectra không có dữ liệu này (dùng direct_response)
- "người có lương X thường chi bao nhiêu" → đây là benchmark question, không phải period comparison
- Các câu chỉ có "so sánh" nhưng KHÔNG kèm 2 mốc thời gian → dùng get_account_summary

Dùng get_account_summary khi user hỏi về 1 period duy nhất:
- "tháng này tôi tiêu bao nhiêu?"
- "chi tiêu tháng 4 là bao nhiêu?"
- "6 tháng gần đây tôi chi bao nhiêu?" (1 khoảng thời gian duy nhất)
- KHÔNG có từ so sánh kèm 2 mốc thời gian khác nhau

QUAN TRỌNG: Nếu user đề cập 2 mốc thời gian bất kỳ TRONG CÙNG 1 CÂU HỎI SO SÁNH → dùng compare_period_spending. Nếu chỉ hỏi 1 khoảng thời gian → dùng get_account_summary.

CÂU HỎI NHIỀU Ý: Nếu câu hỏi gồm nhiều ý khác nhau (vd vừa hỏi chi tiêu, vừa hỏi tiết kiệm), hãy tách MỖI ý thành một task riêng với tool phù hợp (xem MULTI-INTENT DECOMPOSITION). Quy tắc so sánh ở trên chỉ áp dụng trong phạm vi MỘT ý so sánh, không gộp các ý khác nhau lại.

### Section B — DATE RANGE RULES
DATE RANGE RULES:
Ngày hôm nay (Asia/Ho_Chi_Minh): {today_str}

TUẦN:
- "tuần này"   = thứ Hai đầu tuần hiện tại → today+1 (exclusive)
- "tuần trước" = thứ Hai tuần trước → thứ Hai tuần này (exclusive)
Ví dụ nếu today={today_str} ({weekday_vn}):
  tuần này:   period_from={week_monday_str}, period_to={tomorrow_str}
  tuần trước: period_from={last_week_monday_str}, period_to={week_monday_str}

THÁNG:
- "tháng này"   = ngày 1 tháng hiện tại → today+1 (exclusive)
- "tháng trước" = ngày 1 tháng trước → ngày 1 tháng này (exclusive)
Ví dụ nếu today={today_str}:
  tháng này:   period_from={month_start_str}, period_to={tomorrow_str}
  tháng trước: period_from={prev_month_start_str}, period_to={month_start_str}

QUÝ (QUAN TRỌNG — dùng exclusive end):
- Q1: period_from=YYYY-01-01, period_to=YYYY-04-01
- Q2: period_from=YYYY-04-01, period_to=YYYY-07-01  (hoặc today+1 nếu chưa xong)
- Q3: period_from=YYYY-07-01, period_to=YYYY-10-01
- Q4: period_from=YYYY-10-01, period_to=YYYY+1-01-01
Ví dụ nếu today={today_str}:
  Quý hiện tại Q{cur_quarter} (chưa xong): period_from={quarter_start_str}, period_to={tomorrow_str}  ← MTD

NĂM:
- "năm nay"    = YYYY-01-01 → today+1 (exclusive)
- "năm ngoái"  = (YYYY-1)-01-01 → YYYY-01-01 (exclusive)

NGUYÊN TẮC CHUNG:
- Luôn dùng exclusive end convention (period_to là ngày KHÔNG bao gồm)
- "period_to" của full month/quarter = ngày 1 của period tiếp theo
- "period_to" của partial period = today + 1 ngày"""

        return (
            f"Ngay hom nay: {today_str} (Asia/Ho_Chi_Minh timezone).\n"
            f"{prompt_rules}\n"
            f"Cau hoi cua nguoi dung: {chat_request.message}\n"
            f"Pham vi mac dinh cho du lieu tai chinh: {chat_request.scope}.\n"
            f"Ngu canh hoi thoai va bo nho an toan:\n{context}\n"
            "Neu can du lieu ca nhan, hay goi dung mot cong cu phu hop."
        )

    def _get_last_savings_plan(self) -> dict[str, Any] | None:
        if self.session_id:
            state = get_session_state(self.user_id, self.session_id, "last_goal_plan")
            if state:
                return state
        return _LAST_SAVINGS_PLAN.get(self.user_id)

    def _set_last_savings_plan(self, value: dict[str, Any]) -> None:
        _LAST_SAVINGS_PLAN[self.user_id] = dict(value)
        self._set_session_state("last_goal_plan", dict(value))

    def _get_last_budget_plan(self) -> list[dict[str, Any]] | None:
        if self.session_id:
            state = get_session_state(self.user_id, self.session_id, "last_budget_plan")
            budgets = state.get("budgets") if isinstance(state, dict) else None
            if isinstance(budgets, list):
                return [item for item in budgets if isinstance(item, dict)]
        return _LAST_BUDGET_PLAN.get(self.user_id)

    def _set_last_budget_plan(self, budgets: list[dict[str, Any]]) -> None:
        _LAST_BUDGET_PLAN[self.user_id] = list(budgets)
        self._set_session_state("last_budget_plan", {"budgets": budgets})

    def _get_last_category_candidates(self) -> dict[str, Any] | None:
        if self.session_id:
            state = get_session_state(self.user_id, self.session_id, "last_transaction_candidates")
            if state:
                return state
        return _LAST_CATEGORY_CANDIDATES.get(self.user_id)

    def _set_last_category_candidates(self, value: dict[str, Any]) -> None:
        _LAST_CATEGORY_CANDIDATES[self.user_id] = dict(value)
        self._set_session_state("last_transaction_candidates", dict(value))

    def _set_session_state(self, memory_type: str, value: dict[str, Any]) -> None:
        if not self.session_id:
            return
        try:
            save_session_state(self.user_id, self.session_id, memory_type, value)
        except Exception:
            logger.exception("Failed to save chat session state")

    def _pending_preference_from_context(self) -> dict[str, Any] | None:
        if self.session_id:
            state = get_session_state(self.user_id, self.session_id, "conversation_summary")
            candidate = state.get("pending_preference") if isinstance(state, dict) else None
            if isinstance(candidate, dict):
                return candidate
        return None

    def _format_context_for_prompt(self) -> str:
        if not self.chat_context:
            return "Khong co ngu canh hoi thoai da luu."
        compact = {
            "recent_messages": [
                {"role": item.get("role"), "content": item.get("content"), "intent": item.get("intent")}
                for item in list(self.chat_context.get("recent_messages") or [])[-12:]
            ],
            "safe_user_memories": list(self.chat_context.get("safe_user_memories") or [])[:10],
            "last_goal_plan_available": bool(self.chat_context.get("last_goal_plan")),
            "last_budget_plan_available": bool(self.chat_context.get("last_budget_plan")),
            "last_transaction_candidates_available": bool(self.chat_context.get("last_transaction_candidates")),
            "rules": self.chat_context.get("rules") or [],
        }
        return json.dumps(compact, ensure_ascii=False)

    @staticmethod
    def _parse_arguments(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_category_correction(message: str) -> tuple[str, str] | None:
        normalized = ChatSupervisor._fold(message)
        if "bulk" in normalized or "tat ca" in normalized:
            return None
        match = re.search(r"^(?:doi|sua|cap nhat)\s+(.+?)\s+sang\s+(.+)$", normalized)
        if not match:
            return None
        merchant = re.sub(r"^(?:giao dich|khoan)\s+", "", match.group(1).strip(" '\""))
        category = ChatSupervisor._normalize_category_text(match.group(2).strip(" '\""))
        return (merchant, category) if merchant and category else None

    @staticmethod
    def _parse_memory_request(message: str) -> tuple[str, str] | None:
        normalized = ChatSupervisor._fold(message)
        match = re.search(r"(?:lan sau|ghi nho).*?(.+?)\s+(?:vao|la|sang)\s+(.+)$", normalized)
        if not match:
            return None
        pattern = match.group(1).replace("thay", "").strip(" '\"")
        category = ChatSupervisor._normalize_category_text(match.group(2).strip(" '\""))
        return (pattern, category) if pattern and category else None

    @staticmethod
    def _parse_candidate_selection(message: str) -> int | None:
        normalized = ChatSupervisor._fold(message)
        match = re.search(
            r"^(?:chon|toi chon|sua|lay|cai|giao dich)?\s*(?:giao dich|muc|so|thu)?\s*(\d{1,2})$",
            normalized,
        )
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _fold(value: str) -> str:
        value = str(value or "").replace("đ", "d").replace("Đ", "D").replace("Ä‘", "d").replace("Ä", "D")
        folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return " ".join(folded.lower().split())

    @staticmethod
    def _normalize_category_text(value: str) -> str:
        direct = normalize_category(value)
        if direct in CATEGORIES:
            return direct
        folded = ChatSupervisor._fold(value)
        for category in CATEGORIES:
            if ChatSupervisor._fold(category) == folded:
                return category
        return normalize_category(value)

    @staticmethod
    def _is_unsafe_bulk_or_reset(normalized: str) -> bool:
        return any(token in normalized for token in ["xoa het", "reset", "bulk", "tat ca giao dich"])

    @staticmethod
    def _is_memory_affirmation(normalized: str) -> bool:
        return normalized in {"co", "dong y", "yes", "ghi nho", "ghi nho di", "nho di", "ok ghi nho"}

    @staticmethod
    def _parse_preference_memory_request(message: str) -> dict[str, Any] | None:
        candidates = extract_memory_candidates(message, "", [])
        return candidates[0] if candidates else None

    @staticmethod
    def _is_memory_lookup_request(normalized: str) -> bool:
        return any(token in normalized for token in ["ban nho gi ve toi", "nho gi ve toi", "memory cua toi"])

    @staticmethod
    def _is_forget_memory_request(normalized: str) -> bool:
        return any(token in normalized for token in ["quen", "xoa ghi nho", "xoa bo nho"])

    @staticmethod
    def _is_anomaly_question(normalized: str) -> bool:
        return any(
            token in normalized
            for token in [
                "bat thuong",
                "anomaly",
                "giao dich la",
                "dang chu y",
                "rui ro",
                "khoan nao la",
            ]
        )

    @staticmethod
    def _is_forecast_question(normalized: str) -> bool:
        return any(
            token in normalized
            for token in [
                "cuoi thang",
                "con bao nhieu",
                "du doan",
                "forecast",
                "am tien",
                "neu cu tieu",
                "toc do chi tieu",
            ]
        )

    @staticmethod
    def _is_current_balance_question(normalized: str) -> bool:
        return any(
            token in normalized
            for token in [
                "dang co bao tien",
                "toi co bao tien",
                "minh co bao tien",
                "so du hien tai",
                "so tien hien tai",
                "hien tai toi co",
                "hien minh co",
                "con bao tien",
                "con lai bao tien",
                "tai khoan con bao nhieu",
            ]
        )

    @staticmethod
    def _is_financial_health_question(normalized: str) -> bool:
        return any(
            token in normalized
            for token in [
                "suc khoe tai chinh",
                "tai chinh cua toi co on",
                "diem tai chinh",
                "diem cua toi thap",
                "quan ly tien tot",
                "quan ly tien",
                "cai thien diem",
                "tang diem tai chinh",
                "tot hon hay te hon",
                "diem nay co phai diem tin dung",
            ]
        )

    @staticmethod
    def _is_recurring_question(normalized: str) -> bool:
        return any(token in normalized for token in ["khoan dinh ky", "subscription", "co dinh", "lap lai", "hang thang"])

    @staticmethod
    def _is_period_comparison_question(normalized: str) -> bool:
        return any(token in normalized for token in ["so voi thang truoc", "thang nay so voi", "tang giam o dau", "khac gi thang truoc"])

    @staticmethod
    def _is_budget_overrun_explanation_question(normalized: str) -> bool:
        return "ngan sach" in normalized and any(token in normalized for token in ["tai sao", "vi sao", "ly do", "khoan nao lam"])

    @staticmethod
    def _is_category_advice_question(normalized: str) -> bool:
        # "lời khuyên để cắt giảm [category]" — must match BOTH advice intent AND a reduction signal.
        # Gated by "loi khuyen" to avoid catching general "cắt giảm" questions (e.g. B1).
        return "loi khuyen" in normalized and any(
            t in normalized for t in ["cat giam", "giam chi", "tiet giam"]
        )

    @staticmethod
    def _parse_advice_category(normalized: str) -> str:
        # Extract category name from "cat giam [chi phi] X" or "giam chi phi X"
        m = re.search(
            r"(?:cat giam chi phi|giam chi phi|cat giam)\s+([a-z0-9\s]+?)(?:\s+hang\b|\s+moi\b|\s+trong\b|\s*\?|$)",
            normalized,
        )
        return m.group(1).strip() if m else ""

    @staticmethod
    def _is_pct_spending_reduction_question(normalized: str) -> bool:
        # "giảm chi tiêu xuống X%" / "cắt giảm chi tiêu X%" — user wants to reduce total spending by a percentage.
        has_pct = "%" in normalized or "phan tram" in normalized
        has_reduce = any(t in normalized for t in ["giam chi tieu", "cat giam chi tieu", "giam xuong"])
        return has_pct and has_reduce

    @staticmethod
    def _is_cashflow_calendar_question(normalized: str) -> bool:
        return any(token in normalized for token in ["lich dong tien", "ngay nao thieu tien", "ngay nao de thieu", "tu gio toi cuoi thang"])

    @staticmethod
    def _is_debt_question(normalized: str) -> bool:
        return any(token in normalized for token in ["tra gop", "tra no", "khoan no", "con no", "no bao nhieu"])

    @staticmethod
    def _is_emergency_fund_question(normalized: str) -> bool:
        return any(token in normalized for token in ["quy khan cap", "song duoc may thang", "song duoc bao lau", "mat thu nhap"])

    @staticmethod
    def _parse_budget_overrun_category(normalized: str) -> str:
        match = re.search(r"ngan sach\s+(.+?)(?:\?|$)", normalized)
        if not match:
            return ""
        category = match.group(1).strip()
        category = re.sub(r"^(?:nhom|danh muc)\s+", "", category)
        return category

    @staticmethod
    def _parse_months_target(normalized: str) -> int | None:
        match = re.search(r"(\d{1,2})\s*thang", normalized)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_purchase_simulation_request(message: str) -> dict[str, Any] | None:
        normalized = ChatSupervisor._fold(message)
        if "mua" not in normalized and "neu chi" not in normalized and "neu tieu" not in normalized:
            return None
        # "có thể mua X không?" and "nên mua X không?" are feasibility questions
        if not any(token in normalized for token in [
            "co on", "duoc khong", "co sao", "anh huong", "thi sao",
            "co the mua", "nen mua", "co nen mua",
        ]):
            return None
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(trieu|m|k|nghin|ngan)?", normalized)
        if not match:
            return None
        amount = float(match.group(1).replace(",", "."))
        unit = match.group(2) or ""
        if unit in {"trieu", "m"}:
            amount *= 1_000_000
        elif unit in {"k", "nghin", "ngan"}:
            amount *= 1_000
        category = ""
        category_match = re.search(r"mua\s+(.+?)\s+\d", normalized)
        if category_match:
            category = category_match.group(1).strip()
        return {"amount": amount, "category": category}

    @staticmethod
    def _is_summary_question(normalized: str) -> bool:
        if "ngan sach" in normalized:
            return False
        return any(
            token in normalized
            for token in [
                "tong chi",
                "tong thu",
                "thu nhap",
                "chi tieu",
                "tieu nhieu",
                "tieu vao dau",
                "bao nhieu giao dich",
                "co bao nhieu giao dich",
                "tong quan",
                "danh muc",
                "merchant",
                "giao dich",
            ]
        )

    @staticmethod
    def _parse_summary_period(message: str, *, today=None) -> dict[str, str] | None:
        from datetime import date

        current = today or date.today()
        normalized = ChatSupervisor._fold(message)

        def month_range(year: int, month: int) -> dict[str, str] | None:
            if month < 1 or month > 12:
                return None
            start = date(year, month, 1)
            end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
            return {"date_from": start.isoformat(), "date_to": end.isoformat()}

        if any(token in normalized for token in ["thang nay", "thang hien tai"]):
            return month_range(current.year, current.month)

        if "thang truoc" in normalized:
            return month_range(current.year - 1, 12) if current.month == 1 else month_range(current.year, current.month - 1)

        match = re.search(r"\bthang\s+(\d{1,2})(?:\s*(?:/|-|nam)?\s*(\d{4}))?\b", normalized)
        if not match:
            return None
        month = int(match.group(1))
        year = int(match.group(2)) if match.group(2) else current.year
        return month_range(year, month)

    @staticmethod
    def _is_average_question(normalized: str) -> bool:
        return "trung binh" in normalized

    @staticmethod
    def _parse_recent_months(normalized: str) -> int | None:
        """Parse a duration like "6 thang gan day" -> 6.

        Only matches the duration form (digit *before* "thang"), so "thang 6"
        (a specific calendar month) is intentionally not matched.
        """
        match = re.search(r"\b(\d{1,2})\s*thang\b", normalized)
        if not match:
            return None
        n = int(match.group(1))
        if n < 1 or n > 24:
            return None
        return n

    @staticmethod
    def _recent_months_window(months: int, *, today=None) -> dict[str, str]:
        """Return a date_from/date_to window covering the last *months* calendar months."""
        from datetime import date

        current = today or date.today()
        if current.month == 12:
            end = date(current.year + 1, 1, 1)
        else:
            end = date(current.year, current.month + 1, 1)
        m_index = (current.year * 12 + (current.month - 1)) - (months - 1)
        start = date(m_index // 12, m_index % 12 + 1, 1)
        return {"date_from": start.isoformat(), "date_to": end.isoformat()}

    @staticmethod
    def _format_average_spending_answer(data: dict[str, Any], months: int) -> str:
        if not data or not data.get("has_data"):
            return f"Trong {months} tháng gần đây, mình chưa thấy giao dịch nào để tính trung bình."
        currency = str(data.get("currency") or data.get("base_currency") or "VND")
        total_spent = float(data.get("total_spent") or 0)
        total_income = float(data.get("total_income") or 0)
        avg_spent = total_spent / months if months else 0.0
        avg_income = total_income / months if months else 0.0
        lines = [
            f"Trong {months} tháng gần đây, bạn chi tổng cộng {total_spent:,.0f} {currency}, "
            f"trung bình khoảng {avg_spent:,.0f} {currency} mỗi tháng.",
        ]
        if total_income:
            lines.append(f"Thu nhập trung bình khoảng {avg_income:,.0f} {currency} mỗi tháng.")
        return "\n".join(lines)

    @staticmethod
    def _is_multi_intent(message: str, normalized: str) -> bool:
        """Detect a compound question that spans several distinct finance topics.

        Used to stop the deterministic fast-path from answering only one part of a
        multi-intent question; such questions are routed to the planner instead.

        Signal is the number of DISTINCT topic groups present (>=2), or two or more
        explicit question marks. A single conjunction like "và" is intentionally not
        enough, because single questions ("tổng chi và thu tháng 5") use it too.
        """
        if str(message or "").count("?") >= 2:
            return True
        topic_groups = (
            ["chi tieu", "tieu bao nhieu", "tong chi", "tong thu", "thu nhap", "tieu het", "tieu nhieu"],
            ["de danh", "tiet kiem", "muc tieu", "danh duoc", "de ra"],
            ["ngan sach"],
            ["du bao", "so du", "con bao nhieu tien", "cuoi thang con", "cuoi thang"],
            ["dinh ky", "subscription", "thue bao"],
            ["tra no", "khoan no", "tra gop", "con no"],
            ["bat thuong", "giao dich la"],
            ["suc khoe tai chinh", "diem tai chinh", "tai chinh co on", "co on khong", "tai chinh on"],
        )
        matched = 0
        for keywords in topic_groups:
            if any(kw in normalized for kw in keywords):
                matched += 1
                if matched >= 2:
                    return True
        return False

    @staticmethod
    def _is_goal_planning_question(normalized: str) -> bool:
        return any(token in normalized for token in ["tiet kiem", "muc tieu", "dat muc tieu", "de dat"])

    @staticmethod
    def _is_goal_create_request(normalized: str) -> bool:
        return normalized in {"tao muc tieu do di", "tao cai do di", "tao no di", "tao di"} or (
            "tao" in normalized and "muc tieu" in normalized and "do" in normalized
        )

    @staticmethod
    def _is_goal_progress_question(normalized: str) -> bool:
        return any(token in normalized for token in ["tien trien", "tien do", "so voi muc tieu", "muc tieu cua toi"])

    @staticmethod
    def _parse_savings_goal(message: str) -> dict[str, Any] | None:
        from spectra.savings_goals import extract_goal_from_message

        return extract_goal_from_message(message)

    @staticmethod
    def _parse_savings_simulation(message: str) -> dict[str, Any] | None:
        normalized = ChatSupervisor._fold(message)
        if "giam" not in normalized:
            return None
        match = re.search(r"giam\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s*(trieu|m|k|nghin|ngan)?", normalized)
        if not match:
            return None
        amount = float(match.group(2).replace(",", "."))
        unit = match.group(3) or ""
        if unit in {"trieu", "m"}:
            amount *= 1_000_000
        elif unit in {"k", "nghin", "ngan"}:
            amount *= 1_000
        return {"category": match.group(1).strip(), "monthly_reduction": amount}

    @staticmethod
    def _parse_budget_limit_request(message: str) -> dict[str, Any] | None:
        from spectra.budget_planner import parse_budget_limit_request

        return parse_budget_limit_request(message)

    @staticmethod
    def _is_budget_update_request(normalized: str) -> bool:
        return any(token in normalized for token in ["giam ngan sach", "tang ngan sach", "doi ngan sach", "cap nhat ngan sach"])

    @staticmethod
    def _is_budget_apply_request(normalized: str) -> bool:
        return any(
            token in normalized
            for token in ["ap dung ngan sach", "ap dung ke hoach ngan sach", "ap dung ke hoach do", "ap dung cai do"]
        )

    @staticmethod
    def _format_anomaly_answer(data: dict[str, Any]) -> str:
        anomalies = list(data.get("anomalies") or [])[:5]
        summary = data.get("summary") or {}
        if not anomalies:
            return "Minh chua tim thay khoan bat thuong nao trong pham vi hien tai. Neu ban vua ket noi ngan hang, hay thu lai sau khi du lieu duoc dong bo."
        lines = [f"Minh tim thay {summary.get('total', len(anomalies))} khoan bat thuong gan day.", "", "Dang chu y nhat:"]
        for index, item in enumerate(anomalies, start=1):
            lines.append(
                f"{index}. {item.get('merchant')} - {float(item.get('amount') or 0):,.0f} VND - muc {item.get('severity')}"
            )
            reason = str(item.get("reason") or "").strip()
            if reason:
                lines.append(f"   Ly do: {reason}")
        lines.extend(
            [
                "",
                "Goi y: Ban nen kiem tra lai cac khoan nay co dung la chi tieu that khong. Neu dung, hay dua chung vao nhom can theo doi trong ky nay.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_forecast_answer(data: dict[str, Any]) -> str:
        if data.get("available") is False:
            return str(data.get("message") or "Hien tai minh chua co du lieu du bao so du.")
        balance = float(data.get("predicted_end_of_month_balance") or 0)
        avg_daily = float(data.get("avg_daily_spending") or 0)
        days = int(data.get("days_remaining") or 0)
        trend = str(data.get("spending_trend") or "stable")
        recommendation = str(data.get("recommendation") or "")
        return (
            f"Dua tren toc do chi tieu hien tai, so du cuoi thang cua ban duoc uoc tinh con khoang {balance:,.0f} VND.\n\n"
            "Mot vai diem can luu y:\n"
            f"- Chi tieu trung binh moi ngay hien khoang {avg_daily:,.0f} VND.\n"
            f"- Con {days} ngay trong thang.\n"
            f"- Xu huong chi tieu hien tai: {trend}.\n\n"
            f"{recommendation}\n\n"
            "Day chi la uoc tinh, con so thuc te co the thay doi neu ban co khoan chi lon hoac thu nhap phat sinh."
        )

    @staticmethod
    def _format_current_balance_answer(data: dict[str, Any]) -> str:
        if data.get("available") is False:
            return str(data.get("message") or "Hien tai minh chua doc duoc so du tai khoan.")
        current_balance = float(data.get("current_balance") or 0)
        predicted_balance = data.get("predicted_end_of_month_balance")
        lines = [f"Hien tai ban dang co khoang {current_balance:,.0f} VND trong tai khoan da ket noi."]
        if predicted_balance is not None:
            lines.append(
                f"Neu giu toc do chi tieu hien tai, so du cuoi thang duoc uoc tinh con khoang {float(predicted_balance):,.0f} VND."
            )
        lines.append("Con so nay lay tu so du tai khoan mo phong hien tai, khong phai tu lich su chat cu.")
        return "\n\n".join(lines)

    @staticmethod
    def _format_financial_health_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Hien tai minh chua tinh duoc diem suc khoe tai chinh tu du lieu hien co."
        score = int(data.get("score") or 0)
        level = str(data.get("level") or "")
        period = data.get("period") or {}
        label = str(period.get("label") or "ky nay")
        strengths = [str(item) for item in list(data.get("strengths") or [])[:2]]
        risks = [str(item) for item in list(data.get("risks") or [])[:2]]
        actions = [str(item) for item in list(data.get("recommended_actions") or [])[:3]]
        missing = [str(item) for item in list(data.get("missing_data") or [])[:3]]

        lines = [f"Diem suc khoe tai chinh {label} cua ban la {score}/100 - {level}."]
        if strengths:
            lines.extend(["", "Diem tot:"])
            lines.extend(f"- {item}" for item in strengths)
        if risks:
            lines.extend(["", "Diem can chu y:"])
            lines.extend(f"- {item}" for item in risks)
        if actions:
            lines.extend(["", "Goi y cai thien:"])
            lines.extend(f"{index}. {item}" for index, item in enumerate(actions, start=1))
        if missing:
            lines.extend(["", "Du lieu con thieu: " + ", ".join(missing) + "."])
        lines.extend(
            [
                "",
                "Luu y: diem nay chi la cong cu tham khao de quan ly chi tieu va dong tien ca nhan, khong phai diem tin dung hay tu van tai chinh chuyen nghiep.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_account_summary_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Hiện tại mình chưa đọc được tổng hợp thu chi từ dữ liệu hiện có."
        period = data.get("selected_period") or {}
        label = str(period.get("label") or data.get("scope_label") or "giai đoạn này")
        label_text = label[:1].lower() + label[1:] if label else "giai đoạn này"
        currency = str(data.get("currency") or data.get("base_currency") or "VND")
        transaction_count = int(data.get("transaction_count") or 0)
        total_spent = float(data.get("total_spent") or 0)
        total_income = float(data.get("total_income") or 0)
        net_cashflow = total_income - total_spent

        if not data.get("has_data"):
            return f"Trong {label_text}, mình chưa thấy giao dịch nào."

        lines = [
            f"Trong {label_text}, bạn có {transaction_count} giao dịch.",
            f"Tổng chi: {total_spent:,.0f} {currency}; tổng thu: {total_income:,.0f} {currency}; dòng tiền ròng: {net_cashflow:,.0f} {currency}.",
        ]
        by_category = data.get("by_category") if isinstance(data.get("by_category"), dict) else {}
        if by_category:
            category, amount = next(iter(by_category.items()))
            lines.append(f"Chi nhiều nhất là {category}: {float(amount or 0):,.0f} {currency}.")
        uncategorized = int(data.get("uncategorized") or 0)
        if uncategorized:
            lines.append(f"Có {uncategorized} giao dịch chưa được phân loại trong giai đoạn này.")
        return "\n".join(lines)

    @staticmethod
    def _format_savings_plan_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Hiện tại mình chưa lập được kế hoạch tiết kiệm từ dữ liệu hiện có."
        goal = data.get("goal") or {}
        required = data.get("required_plan") or {}
        feasibility = data.get("feasibility") or {}
        actions = list(data.get("next_actions") or [])[:3]
        adjustments = list(data.get("recommended_adjustments") or [])[:2]
        label_map = {
            "achieved": "đã đạt",
            "realistic": "khả thi",
            "challenging": "khá thử thách",
            "risky": "rủi ro",
            "unrealistic": "khó đạt",
            "insufficient_data": "thiếu dữ liệu",
        }
        label = str(feasibility.get("label") or "")
        lines = [
            f"Để tiết kiệm {float(goal.get('target_amount') or 0):,.0f} {goal.get('currency', 'VND')} trước {goal.get('target_date')}, "
            f"bạn cần để dành khoảng {float(required.get('required_monthly_saving') or 0):,.0f} VND/tháng.",
            "",
            f"Đánh giá: {label_map.get(label, label)} - {feasibility.get('reason')}",
        ]
        if adjustments:
            lines.extend(["", "Gợi ý cắt giảm:"])
            for item in adjustments:
                lines.append(
                    f"- {item.get('category')}: giảm khoảng {float(item.get('suggested_reduction') or 0):,.0f} VND/tháng."
                )
        if actions:
            lines.extend(["", "Bước tiếp theo:"])
            lines.extend(f"{index}. {item}" for index, item in enumerate(actions, start=1))
        lines.extend(["", "Bạn có muốn mình tạo mục tiêu này để theo dõi không?"])
        lines.append("Lưu ý: đây là ước tính dựa trên dữ liệu hiện có, không phải tư vấn tài chính chuyên nghiệp.")
        return "\n".join(lines)

    @staticmethod
    def _format_savings_simulation_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Mình chưa mô phỏng được kịch bản này."
        impact = data.get("impact") or {}
        return (
            f"Nếu áp dụng điều chỉnh này, khoảng cách hằng tháng thay đổi từ "
            f"{float(impact.get('monthly_gap_before') or 0):,.0f} VND lên "
            f"{float(impact.get('monthly_gap_after') or 0):,.0f} VND.\n\n"
            f"Mức khả thi chuyển từ {impact.get('label_before')} sang {impact.get('label_after')}.\n\n"
            "Đây chỉ là mô phỏng ngân sách, không cập nhật giao dịch hay budget của bạn."
        )

    @staticmethod
    def _format_savings_goals_answer(data: dict[str, Any]) -> str:
        goals = list(data.get("goals") or [])
        if not goals:
            return "Mình chưa thấy mục tiêu tiết kiệm đang hoạt động nào. Bạn có thể tạo một mục tiêu mới, ví dụ tiết kiệm 20 triệu trong 6 tháng."
        if len(goals) > 1:
            lines = ["Bạn đang có nhiều mục tiêu tiết kiệm. Bạn muốn xem mục tiêu nào?"]
            for index, goal in enumerate(goals[:5], start=1):
                lines.append(f"{index}. {goal.get('name')} - còn {float(goal.get('remaining_amount') or 0):,.0f} {goal.get('currency', 'VND')}")
            return "\n".join(lines)
        goal = goals[0]
        target = float(goal.get("target_amount") or 0)
        current = float(goal.get("current_amount") or 0)
        progress = (current / target * 100) if target > 0 else 0
        return (
            f"Mục tiêu {goal.get('name')} đang đạt khoảng {progress:.0f}%.\n\n"
            f"Bạn đã có {current:,.0f} / {target:,.0f} {goal.get('currency', 'VND')}, "
            f"còn cần {float(goal.get('remaining_amount') or 0):,.0f} trước {goal.get('target_date')}."
        )

    @staticmethod
    def _format_budget_status_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Minh chua doc duoc trang thai ngan sach hien tai."
        currency = str(data.get("currency") or "VND")
        summary = data.get("summary") or {}
        alerts = list(data.get("alerts") or [])
        categories = list(data.get("categories") or [])
        lines = [
            f"Tong ngan sach hien tai: {float(summary.get('total_budget') or 0):,.0f} {currency}.",
            f"Da chi: {float(summary.get('total_spent') or 0):,.0f} {currency}.",
        ]
        if summary.get("usage_percentage") is not None:
            lines.append(f"Da dung khoang {float(summary.get('usage_percentage') or 0):.1f}% ngan sach.")
        if alerts:
            lines.extend(["", "Can chu y:"])
            lines.extend(f"- {item}" for item in alerts[:3])
        else:
            lines.extend(["", "Hien chua thay danh muc nao vuot ngan sach theo du lieu hien co."])
        tracked = [item for item in categories if item.get("budget_limit")]
        if tracked:
            lines.extend(["", "Mot so danh muc:"])
            for item in tracked[:5]:
                lines.append(
                    f"- {item.get('category')}: da chi {float(item.get('actual_spend') or 0):,.0f}/{float(item.get('budget_limit') or 0):,.0f} {currency} ({item.get('status')})."
                )
        lines.append("")
        lines.append("Day la uoc tinh dua tren toc do chi tieu hien tai.")
        return "\n".join(lines)

    @staticmethod
    def _format_budget_recommendation_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Minh chua tao duoc de xuat ngan sach tu du lieu hien co."
        currency = str(data.get("currency") or "VND")
        summary = data.get("summary") or {}
        recs = list(data.get("recommended_budgets") or [])[:5]
        lines = [
            "Dua tren du lieu hien co, minh de xuat ngan sach ky nay nhu sau:",
            "",
        ]
        if summary:
            lines.append(
                f"Thu nhap: {float(summary.get('total_income') or 0):,.0f} {currency}; "
                f"muc tiet kiem muc tieu: {float(summary.get('target_savings') or 0):,.0f} {currency}."
            )
            lines.append("")
        for item in recs:
            lines.append(
                f"- {item.get('category')}: {float(item.get('recommended_budget') or 0):,.0f} {currency} "
                f"({item.get('difficulty')})"
            )
        risks = list(data.get("risks") or [])[:2]
        if risks:
            lines.extend(["", "Rui ro:"])
            lines.extend(f"- {risk}" for risk in risks)
        actions = list(data.get("next_actions") or [])[:3]
        if actions:
            lines.extend(["", "Buoc tiep theo:"])
            lines.extend(f"{index}. {action}" for index, action in enumerate(actions, start=1))
        lines.extend(["", "Ban co muon minh ap dung ke hoach ngan sach nay khong?"])
        lines.append("Day la goi y quan ly ngan sach, khong phai tu van tai chinh chuyen nghiep.")
        return "\n".join(lines)

    @staticmethod
    def _format_budget_simulation_answer(data: dict[str, Any]) -> str:
        if not data:
            return "Minh chua mo phong duoc thay doi ngan sach nay."
        impact = data.get("impact") or {}
        return (
            f"Neu ap dung thay doi nay, tong ngan sach thay doi {float(impact.get('budget_delta') or 0):,.0f} VND.\n\n"
            f"Muc tiet kiem uoc tinh thay doi {float(impact.get('estimated_saving_change') or 0):,.0f} VND.\n"
            f"Vuot ngan sach du kien truoc/sau: {float(impact.get('projected_over_budget_before') or 0):,.0f} -> "
            f"{float(impact.get('projected_over_budget_after') or 0):,.0f} VND.\n\n"
            "Day chi la mo phong, minh chua cap nhat ngan sach that."
        )

    @staticmethod
    def _format_recurring_answer(data: dict[str, Any]) -> str:
        items = list(data.get("items") or [])
        summary = data.get("summary") or {}
        if not items:
            return "Minh chua tim thay khoan dinh ky nao tu du lieu hien co."
        lines = [
            f"Minh tim thay {summary.get('active_count', len(items))} khoan co dau hieu dinh ky.",
            f"Uoc tinh chi dinh ky moi thang: {float(summary.get('monthly_estimate') or 0):,.0f} VND.",
            "",
            "Dang chu y:",
        ]
        for item in items[:5]:
            lines.append(
                f"- {item.get('merchant')}: khoang {float(item.get('monthly_estimate') or 0):,.0f} VND/thang ({item.get('kind')})."
            )
        if summary.get("price_change_count"):
            lines.append(f"Co {summary.get('price_change_count')} khoan co dau hieu thay doi gia.")
        lines.append("Day la uoc tinh tu lich su giao dich, khong phai lich thanh toan chac chan.")
        return "\n".join(lines)

    @staticmethod
    def _format_period_comparison_answer(data: dict[str, Any]) -> str:
        totals = data.get("totals") or {}
        categories = list(data.get("category_deltas") or [])[:3]
        spent_delta = float(totals.get("spent_delta") or 0)
        direction = "nhieu hon" if spent_delta > 0 else "it hon" if spent_delta < 0 else "bang"
        lines = [
            f"So voi ky truoc, ky hien tai chi {direction} {abs(spent_delta):,.0f} VND.",
            f"Chi ky hien tai: {float(totals.get('period_a_spent') or 0):,.0f} VND; ky truoc: {float(totals.get('period_b_spent') or 0):,.0f} VND.",
        ]
        if categories:
            lines.extend(["", "Danh muc thay doi manh nhat:"])
            for item in categories:
                lines.append(f"- {item.get('category')}: {float(item.get('delta') or 0):+,.0f} VND.")
        return "\n".join(lines)

    @staticmethod
    def _format_budget_overrun_explanation(data: dict[str, Any]) -> str:
        categories = list(data.get("categories") or [])
        if not categories:
            return "Minh chua thay danh muc nao vuot hoac co nguy co vuot ngan sach trong du lieu hien co."
        lines = ["Ly do chinh:"]
        for item in categories[:3]:
            lines.append(
                f"- {item.get('category')}: da chi {float(item.get('actual_spend') or 0):,.0f}/{float(item.get('budget_limit') or 0):,.0f} VND."
            )
            drivers = list(item.get("top_drivers") or [])[:3]
            if drivers:
                lines.append("  Giao dich lon:")
                for tx in drivers:
                    lines.append(f"  - {tx.get('date')} {tx.get('merchant')}: {float(tx.get('amount') or 0):,.0f} VND")
        lines.append("Goi y: uu tien giam cac khoan phat sinh trong danh muc dang vuot cho toi cuoi ky.")
        return "\n".join(lines)

    @staticmethod
    def _format_cashflow_calendar_answer(data: dict[str, Any]) -> str:
        risk_days = list(data.get("risk_days") or [])
        upcoming = list(data.get("upcoming_events") or [])[:5]
        lines = [
            f"Dua tren du lieu hien co, so du hien tai khoang {float(data.get('current_balance') or 0):,.0f} VND.",
            f"Chi tieu trung binh ngay uoc tinh: {float(data.get('avg_daily_spending') or 0):,.0f} VND.",
        ]
        if risk_days:
            lines.append(f"Co nguy co am tien tu ngay {risk_days[0].get('date')}.")
        else:
            lines.append("Trong khoang uoc tinh nay, minh chua thay ngay nao bi am tien.")
        if upcoming:
            lines.extend(["", "Khoan dinh ky sap toi:"])
            for event in upcoming:
                lines.append(f"- {event.get('estimated_date')} {event.get('merchant')}: {float(event.get('amount') or 0):+,.0f} VND")
        lines.append("Lich nay la uoc tinh, khong phai lich thanh toan chac chan.")
        return "\n".join(lines)

    @staticmethod
    def _format_purchase_impact_answer(data: dict[str, Any]) -> str:
        purchase = data.get("purchase") or {}
        impact = data.get("impact") or {}
        recommendation = data.get("recommendation") or {}
        return (
            f"Neu chi {float(purchase.get('amount') or 0):,.0f} VND cho khoan nay, "
            f"so du cuoi thang uoc tinh se con {float(impact.get('predicted_end_balance_after') or 0):,.0f} VND.\n\n"
            f"Danh gia: {recommendation.get('label')} - {recommendation.get('reason')}\n\n"
            "Day chi la mo phong, minh chua ghi nhan giao dich moi."
        )

    @staticmethod
    def _format_debt_summary_answer(data: dict[str, Any]) -> str:
        summary = data.get("summary") or {}
        items = list(data.get("items") or [])
        if not items:
            return "Minh chua thay khoan thanh toan co dau hieu no/tra gop trong pham vi hien tai. Luu y: he thong chua co du lieu du no con lai."
        lines = [
            f"Minh thay {summary.get('debt_like_payment_count', 0)} khoan thanh toan co dau hieu no/tra gop.",
            f"Tong da tra trong pham vi nay: {float(summary.get('debt_like_paid_amount') or 0):,.0f} VND.",
            "",
            "Nguon chi chinh:",
        ]
        for item in items[:5]:
            lines.append(f"- {item.get('merchant')}: {float(item.get('paid_amount') or 0):,.0f} VND.")
        lines.append("Minh chua co du lieu du no con lai, nen khong ket luan tong no hien tai.")
        return "\n".join(lines)

    @staticmethod
    def _format_emergency_fund_answer(data: dict[str, Any]) -> str:
        covered = data.get("estimated_months_covered")
        covered_text = "chua tinh duoc" if covered is None else f"{float(covered):.1f} thang"
        return (
            f"Quy khan cap hien tai uoc tinh bao phu {covered_text} chi phi thiet yeu.\n\n"
            f"Chi phi thiet yeu moi thang uoc tinh: {float(data.get('monthly_essential_spend') or 0):,.0f} VND.\n"
            f"Muc tieu {float(data.get('months_target') or 3):.0f} thang can khoang {float(data.get('target_amount') or 0):,.0f} VND; "
            f"con thieu khoang {float(data.get('gap_amount') or 0):,.0f} VND.\n\n"
            f"Trang thai: {data.get('status')}."
        )


    @staticmethod
    def _infer_intent(message: str, traces: list[ChatToolCallTrace]) -> ChatIntent:
        if traces:
            tool_name = traces[0].tool_name
            if tool_name == "get_account_summary":
                return ChatIntent.SPENDING_BREAKDOWN
            if tool_name == "get_transactions":
                return ChatIntent.CATEGORY_ANALYSIS
            if tool_name in {"get_category_options", "get_category_rules", "get_learning_summary", "test_category_rule"}:
                return ChatIntent.CATEGORY_ANALYSIS
            if tool_name in {"get_anomalies", "explain_anomaly"}:
                return ChatIntent.ANOMALY_EXPLANATION
            if tool_name == "get_balance_forecast":
                return ChatIntent.FORECAST_BALANCE
            if tool_name in {"get_financial_health_score", "get_peer_benchmark"}:
                return ChatIntent.FINANCIAL_HEALTH_SCORE
            if tool_name in {
                "plan_savings_goal",
                "simulate_savings_adjustment",
                "get_savings_goals",
                "create_savings_goal",
                "update_savings_goal",
                "archive_savings_goal",
            }:
                return ChatIntent.SAVING_SUGGESTION
            if tool_name in {
                "get_budget_status",
                "recommend_budget_plan",
                "simulate_budget_adjustment",
                "compare_budget_vs_actual",
                "update_budget_limit",
                "upsert_budget_plan",
                "explain_budget_overrun",
                "simulate_purchase_impact",
                "get_debt_summary",
                "get_emergency_fund_status",
            }:
                return ChatIntent.SAVING_SUGGESTION
            if tool_name in {"get_recurring_transactions", "compare_period_spending"}:
                return ChatIntent.SPENDING_BREAKDOWN
            if tool_name == "get_cashflow_calendar":
                return ChatIntent.FORECAST_BALANCE
            if tool_name == "get_current_user":
                return ChatIntent.ACCOUNT_SUMMARY
        lower = ChatSupervisor._fold(message)
        if any(word in lower for word in ["chi tieu", "spending", "danh muc"]):
            return ChatIntent.SPENDING_BREAKDOWN
        if any(word in lower for word in ["tai khoan", "account number", "mat khau", "password", "token", "api key", "rieng tu", "privacy", "ca nhan"]):
            return ChatIntent.PRIVACY_OR_PERMISSION
        return ChatIntent.GENERAL_FINANCE_ADVICE
