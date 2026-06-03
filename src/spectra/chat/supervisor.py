"""OpenAI-backed chatbot supervisor with Phase 3 confirmation flows."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from fastapi import Request

from spectra.categories import CATEGORIES, normalize_category
from spectra.chat.confirmation import PendingAction, pending_actions
from spectra.chat.executor import ToolExecutor
from spectra.chat.memory import extract_memory_candidates, get_session_state, save_session_state, upsert_user_memory
from spectra.chat.models import ChatConfirmation, ChatIntent, ChatRequest, ChatResponse, ChatToolCallTrace, SuggestedAction
from spectra.chat.prompts import SUPERVISOR_SYSTEM_PROMPT
from spectra.chat.tools import openai_tool_definitions
from spectra.config import Settings, load_settings

logger = logging.getLogger("spectra.chat")

_SAFE_DEFAULT_MODEL = "gpt-4o-mini"
_UNSUPPORTED_KEYWORDS: dict[ChatIntent, list[str]] = {}
_INVESTMENT_KEYWORDS = ["mua co phieu", "ban co phieu", "crypto", "coin", "chung khoan", "buy stock", "sell stock"]
_LAST_CATEGORY_CORRECTIONS: dict[str, dict[str, Any]] = {}
_LAST_CATEGORY_CANDIDATES: dict[str, dict[str, Any]] = {}
_LAST_SAVINGS_PLAN: dict[str, dict[str, Any]] = {}
_LAST_BUDGET_PLAN: dict[str, list[dict[str, Any]]] = {}


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
        confirmation_response = await self._handle_confirmation_request(chat_request)
        if confirmation_response:
            return confirmation_response

        deterministic = self._handle_phase3_category_flow(chat_request)
        if deterministic:
            return deterministic

        phase4 = await self._handle_phase4_read_flow(chat_request)
        if phase4:
            return phase4

        early = self._guardrail_response(chat_request)
        if early:
            return early

        api_key = self.settings.openai_api_key
        if not api_key:
            raise MissingOpenAIKeyError("OPENAI_API_KEY is missing")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=30.0)
            model = self.settings.openai_model or _SAFE_DEFAULT_MODEL
            messages = [
                {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_message(chat_request)},
            ]
            first = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tool_definitions(),
                tool_choice="auto",
                parallel_tool_calls=False,
                temperature=0.2,
            )
            assistant_message = first.choices[0].message
            messages.append(assistant_message.model_dump(exclude_none=True))
            traces: list[ChatToolCallTrace] = []

            tool_calls = list(assistant_message.tool_calls or [])[:1]
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = self._parse_arguments(tool_call.function.arguments)
                result = await self.executor.execute(tool_name, arguments)
                traces.append(
                    ChatToolCallTrace(
                        tool_name=tool_name,
                        arguments=arguments,
                        status=result.status,
                        error=result.error,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result.model_dump(), ensure_ascii=False),
                    }
                )

            if tool_calls:
                final = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
                answer = final.choices[0].message.content or "Xin loi, minh chua the tao cau tra loi."
            else:
                answer = assistant_message.content or "Xin loi, minh chua the tao cau tra loi."

            intent = self._infer_intent(chat_request.message, traces)
            return ChatResponse(
                answer=answer,
                intent=intent,
                tool_calls=traces,
                debug={"model": model} if chat_request.debug else None,
            )
        except MissingOpenAIKeyError:
            raise
        except Exception:
            logger.exception("Chat supervisor failed")
            return ChatResponse(
                answer="Xin loi, hien minh chua the xu ly cau hoi nay. Vui long thu lai sau.",
                intent=ChatIntent.UNKNOWN,
                tool_calls=[],
            )

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
        budget_flow = await self._handle_phase7_budget_flow(chat_request, normalized)
        if budget_flow:
            return budget_flow

        goal_flow = await self._handle_phase6_savings_goal_flow(chat_request, normalized)
        if goal_flow:
            return goal_flow

        if self._is_financial_health_question(normalized):
            arguments = {"scope": chat_request.scope, "refresh": False}
            result = await self.executor.execute("get_financial_health_score", arguments)
            trace = ChatToolCallTrace(
                tool_name="get_financial_health_score",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            return ChatResponse(
                answer=self._format_financial_health_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.FINANCIAL_HEALTH_SCORE,
                tool_calls=[trace],
            )

        if self._is_anomaly_question(normalized):
            arguments = {"limit": 10, "scope": "cycle"}
            result = await self.executor.execute("get_anomalies", arguments)
            trace = ChatToolCallTrace(
                tool_name="get_anomalies",
                arguments=arguments,
                status=result.status,
                error=result.error,
            )
            return ChatResponse(
                answer=self._format_anomaly_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.ANOMALY_EXPLANATION,
                tool_calls=[trace],
            )

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
            return ChatResponse(
                answer=answer,
                intent=ChatIntent.FORECAST_BALANCE,
                tool_calls=[trace],
            )
        return None

    async def _handle_phase7_budget_flow(self, chat_request: ChatRequest, normalized: str) -> ChatResponse | None:
        if "ngan sach" not in normalized and not self._is_budget_apply_request(normalized):
            return None

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

        parsed_sim = self._parse_budget_limit_request(chat_request.message)
        if parsed_sim and any(token in normalized for token in ["neu", "thi co", "dat muc"]):
            arguments = {"scope": chat_request.scope, "adjustments": [parsed_sim]}
            result = await self.executor.execute("simulate_budget_adjustment", arguments)
            trace = ChatToolCallTrace(tool_name="simulate_budget_adjustment", arguments=arguments, status=result.status, error=result.error)
            return ChatResponse(
                answer=self._format_budget_simulation_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        if any(token in normalized for token in ["vuot ngan sach", "dang vuot", "danh muc nao", "so sanh"]):
            tool = "compare_budget_vs_actual" if "so sanh" in normalized else "get_budget_status"
            arguments = {"scope": chat_request.scope}
            result = await self.executor.execute(tool, arguments)
            trace = ChatToolCallTrace(tool_name=tool, arguments=arguments, status=result.status, error=result.error)
            return ChatResponse(
                answer=self._format_budget_status_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        if any(token in normalized for token in ["nen dat", "chia ngan sach", "tao ngan sach", "hop ly", "dieu chinh ngan sach"]):
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
            return ChatResponse(
                answer=self._format_budget_recommendation_answer(data),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
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
            return ChatResponse(
                answer=self._format_savings_goals_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

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
            return ChatResponse(
                answer=self._format_savings_simulation_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )

        plan_args = self._parse_savings_goal(chat_request.message)
        if plan_args and self._is_goal_planning_question(normalized):
            result = await self.executor.execute("plan_savings_goal", plan_args)
            trace = ChatToolCallTrace(tool_name="plan_savings_goal", arguments=plan_args, status=result.status, error=result.error)
            if result.status == "success":
                self._set_last_savings_plan(dict(plan_args))
            return ChatResponse(
                answer=self._format_savings_plan_answer(result.data if isinstance(result.data, dict) else {}),
                intent=ChatIntent.SAVING_SUGGESTION,
                tool_calls=[trace],
            )
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
        context = self._format_context_for_prompt()
        return (
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

    def _guardrail_response(self, chat_request: ChatRequest) -> ChatResponse | None:
        message = self._fold(chat_request.message)
        if any(keyword in message for keyword in _INVESTMENT_KEYWORDS):
            return ChatResponse(
                answer=(
                    "Minh khong the dua ra khuyen nghi mua, ban hoac nam giu co phieu, crypto hay san pham dau tu. "
                    "Minh co the giup ban xem ngan sach, dong tien va thoi quen tiet kiem."
                ),
                intent=ChatIntent.OUT_OF_SCOPE_INVESTMENT_ADVICE,
            )
        for intent, keywords in _UNSUPPORTED_KEYWORDS.items():
            if any(keyword in message for keyword in keywords):
                return ChatResponse(
                    answer="Chuc nang nay se duoc them o phase sau. Hien tai minh co the giup ban xem tong quan chi tieu, xem giao dich, danh muc va sua category giao dich.",
                    intent=intent,
                )
        return None

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
            if tool_name == "get_financial_health_score":
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
            }:
                return ChatIntent.SAVING_SUGGESTION
            if tool_name == "get_current_user":
                return ChatIntent.ACCOUNT_SUMMARY
        lower = ChatSupervisor._fold(message)
        if any(word in lower for word in ["chi tieu", "spending", "danh muc"]):
            return ChatIntent.SPENDING_BREAKDOWN
        return ChatIntent.GENERAL_FINANCE_ADVICE
