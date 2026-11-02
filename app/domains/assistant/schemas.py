from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssistantStatus(BaseModel):
    available: bool
    reason: str | None  # "sin_llave" | "deshabilitado" | "sin_presupuesto" | None
    model: str
    model_name: str
    budget_usd: Decimal
    spent_usd: Decimal
    remaining_usd: Decimal


class ConversationLite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class StepRead(BaseModel):
    name: str
    ok: bool
    summary: str | None = None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tool_name: str
    summary: str
    args: dict[str, Any]
    proposal_id: str | None
    proposal_kind: str | None = None
    status: str
    resolved_at: datetime | None
    created_at: datetime


class MessageRead(BaseModel):
    id: str
    role: str
    text: str | None
    steps: list[StepRead]
    actions: list[ActionRead]
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    created_at: datetime


class ConversationRead(BaseModel):
    id: str
    title: str | None
    busy: bool
    messages: list[MessageRead]
    created_at: datetime
    updated_at: datetime


class MessageSend(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class UsageRow(BaseModel):
    key: str
    label: str
    calls: int
    cost_usd: Decimal


class UsageRead(BaseModel):
    month: str
    budget_usd: Decimal
    total_usd: Decimal
    calls: int
    by_user: list[UsageRow]
    by_day: list[UsageRow]
