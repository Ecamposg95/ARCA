from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CashCutCreate(BaseModel):
    financial_account_id: str
    date: date_type


class CashCutCount(BaseModel):
    counted_amount: Decimal = Field(ge=0, allow_inf_nan=False)
    # Obligatoria cuando contado ≠ esperado; el backend lo exige.
    explanation: str | None = Field(default=None, max_length=500)


class CashCutDeliver(BaseModel):
    delivered_amount: Decimal = Field(gt=0, allow_inf_nan=False)
    delivered_to_account_id: str


class CashCutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    financial_account_id: str
    account_name: str | None = None
    business_unit_id: str | None = None
    business_unit_name: str | None = None
    date: date_type
    opening_balance: Decimal
    inflows: Decimal
    outflows: Decimal
    expected_closing: Decimal
    counted_amount: Decimal | None
    difference: Decimal | None
    explanation: str | None
    status: str
    delivered_amount: Decimal | None
    delivered_to_account_id: str | None
    delivered_to_account_name: str | None = None
    delivered_by: str | None
    delivered_by_name: str | None = None
    delivered_at: datetime | None
    received_by: str | None
    received_by_name: str | None = None
    received_at: datetime | None
    transfer_group_id: str | None
    adjustment_transaction_id: str | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class TodayCashRow(BaseModel):
    """Una caja de efectivo hoy: su saldo y si ya tiene corte."""

    account_id: str
    account_name: str
    business_unit_id: str | None
    business_unit_name: str | None
    current_balance: Decimal
    cut: CashCutRead | None
