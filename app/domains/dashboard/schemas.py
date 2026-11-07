"""Respuesta de `GET /dashboard/today` (Inicio «Tablero del día»)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class MoneyRow(BaseModel):
    key: Literal["central", "branches", "banks", "processor"]
    label: str
    amount: Decimal
    status: Literal["CONFIRMED", "PROVISIONAL", "TO_COLLECT", "TO_DEPOSIT"] | None


class NextSettlement(BaseModel):
    account: str
    amount: Decimal
    expected_on: date


class MoneyPanel(BaseModel):
    total: Decimal
    available: Decimal
    in_transit: Decimal
    previous_close: Decimal
    delta: Decimal
    rows: list[MoneyRow]
    next_settlement: NextSettlement | None
    needs_opening: bool


class WeekDay(BaseModel):
    date: date
    amount: Decimal
    pending_approval_amount: Decimal


class WeekItem(BaseModel):
    payable_id: str
    due_date: date
    overdue: bool
    vendor: str
    description: str
    amount: Decimal
    running_balance: Decimal
    approval: Literal["PENDING", "REQUIRED"] | None


class WeekPanel(BaseModel):
    start: date
    end: date
    days: list[WeekDay]
    items: list[WeekItem]
    total: Decimal


class PendingApproval(BaseModel):
    proposal_id: str
    summary: str
    amount: Decimal | None
    requested_by_name: str | None


class ApprovalsPanel(BaseModel):
    pending: list[PendingApproval]
    can_authorize: bool


class SparkPoint(BaseModel):
    date: date
    value: Decimal


class BranchRow(BaseModel):
    business_unit_id: str
    name: str
    sales: Decimal
    share: Decimal
    delta_pct: Decimal | None
    delta_basis: Literal["previous_year", "avg_3m"] | None
    sparkline: list[SparkPoint]
    cut: Literal["DELIVERED", "LATE", "MISSING", "NA"]


class BranchesPanel(BaseModel):
    month: date | None
    origin: Literal["live", "historical"]
    rows: list[BranchRow]


class DashboardToday(BaseModel):
    money: MoneyPanel
    week: WeekPanel
    approvals: ApprovalsPanel
    branches: BranchesPanel
