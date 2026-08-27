from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecurringCreate(BaseModel):
    kind: Literal["INCOME", "EXPENSE"]
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0, allow_inf_nan=False)  # TOTAL con impuesto
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1, allow_inf_nan=False)
    category_id: str
    project_id: str | None = None
    customer_id: str | None = None
    vendor_id: str | None = None
    financial_account_id: str | None = None
    # 1–28: la regla de la casa para no pelear con febrero.
    day_of_month: int = Field(default=1, ge=1, le=28)
    notes: str | None = Field(default=None, max_length=1000)


class RecurringUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    financial_account_id: str | None = None
    status: Literal["ACTIVE", "PAUSED"] | None = None
    notes: str | None = Field(default=None, max_length=1000)


class GenerateRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class RecurringRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    description: str
    amount: Decimal
    tax_rate: Decimal
    category_id: str
    project_id: str | None
    customer_id: str | None
    vendor_id: str | None
    financial_account_id: str | None
    day_of_month: int
    status: str
    notes: str | None
    created_at: datetime
