"""Pydantic models for the chatbot API and tool layer."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatIntent(str, Enum):
    ACCOUNT_SUMMARY = "ACCOUNT_SUMMARY"
    SPENDING_BREAKDOWN = "SPENDING_BREAKDOWN"
    CATEGORY_ANALYSIS = "CATEGORY_ANALYSIS"
    ANOMALY_EXPLANATION = "ANOMALY_EXPLANATION"
    FORECAST_BALANCE = "FORECAST_BALANCE"
    SAVING_SUGGESTION = "SAVING_SUGGESTION"
    CATEGORY_CORRECTION = "CATEGORY_CORRECTION"
    FINANCIAL_HEALTH_SCORE = "FINANCIAL_HEALTH_SCORE"
    GENERAL_FINANCE_ADVICE = "GENERAL_FINANCE_ADVICE"
    PRIVACY_OR_PERMISSION = "PRIVACY_OR_PERMISSION"
    OUT_OF_SCOPE_INVESTMENT_ADVICE = "OUT_OF_SCOPE_INVESTMENT_ADVICE"
    UNKNOWN = "UNKNOWN"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    scope: Literal["cycle", "90d", "ytd"] = "cycle"
    debug: bool = False
    confirmation_id: str | None = None
    confirm: bool | None = None


class ChatToolCallTrace(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "error", "rejected"]
    error: str | None = None


class SuggestedAction(BaseModel):
    label: str
    action: str | None = None
    type: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmation_id: str | None = None


class ChatConfirmation(BaseModel):
    confirmation_id: str
    action_type: str
    summary: str


class ChatResponse(BaseModel):
    session_id: str | None = None
    message_id: str | None = None
    answer: str
    intent: ChatIntent = ChatIntent.UNKNOWN
    tool_calls: list[ChatToolCallTrace] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmation: ChatConfirmation | None = None
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    memory_updates: list[dict[str, Any]] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class ToolExecutionResult(BaseModel):
    tool_name: str
    status: Literal["success", "error", "rejected"]
    data: dict[str, Any] | list[Any] | None = None
    error: str | None = None


class RegisteredTool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    required_scope: str
    requires_session: bool = True
    read_only: bool = True
    dangerous: bool = False
