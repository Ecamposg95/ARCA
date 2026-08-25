from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

FinancialAccountType = Literal["CASH", "BANK", "CREDIT_CARD", "OTHER"]


class FinancialAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: FinancialAccountType
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    institution: str | None = Field(default=None, max_length=100)
    last_four: str | None = Field(default=None, max_length=4)
    credit_limit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class FinancialAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    institution: str | None = Field(default=None, max_length=100)
    last_four: str | None = Field(default=None, max_length=4)
    active: bool | None = None


class FinancialAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    credit_limit: Decimal | None = None
    currency: str
    opening_balance: Decimal
    current_balance: Decimal
    institution: str | None
    last_four: str | None
    active: bool
    created_at: datetime

    @computed_field
    @property
    def is_liability(self) -> bool:
        """Una tarjeta registra deuda: su saldo es lo que debes, no lo que tienes."""
        return self.type in ("CREDIT_CARD",)

    @computed_field
    @property
    def available_credit(self) -> Decimal | None:
        if self.credit_limit is None or not self.is_liability:
            return None
        return self.credit_limit - self.current_balance
