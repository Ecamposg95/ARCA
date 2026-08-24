from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class PayableCreate(BaseModel):
    vendor_id: str
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    date: date_type | None = None  # registro del compromiso; default hoy
    due_date: date_type
    category_id: str
    notes: str | None = Field(default=None, max_length=1000)


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    financial_account_id: str
    date: date_type | None = None


class DebtCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PayableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_id: str
    description: str
    amount: Decimal
    amount_paid: Decimal
    date: date_type
    due_date: date_type
    category_id: str
    status: str
    notes: str | None
    created_at: datetime

    @computed_field
    @property
    def balance(self) -> Decimal:
        return self.amount - self.amount_paid

    @computed_field
    @property
    def is_overdue(self) -> bool:
        return self.status in ("OPEN", "PARTIAL") and self.due_date < date_type.today()

    @computed_field
    @property
    def display_status(self) -> str:
        return "OVERDUE" if self.is_overdue else self.status
