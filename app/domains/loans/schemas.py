from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LoanCreate(BaseModel):
    lender: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    principal: Decimal = Field(gt=0, allow_inf_nan=False)
    # Tasa ANUAL: 0.24 = 24%. Se convierte a mensual al amortizar.
    annual_rate: Decimal = Field(default=Decimal("0"), ge=0, le=2, allow_inf_nan=False)
    term_months: int = Field(gt=0, le=600)
    start_date: date_type
    payment_day: int = Field(default=1, ge=1, le=28)
    financial_account_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)


class LoanPaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    financial_account_id: str
    date: date_type | None = None


class LoanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lender: str
    description: str
    principal: Decimal
    outstanding: Decimal
    annual_rate: Decimal
    term_months: int
    start_date: date_type
    payment_day: int
    financial_account_id: str | None
    status: str
    notes: str | None
    created_at: datetime

    # Lo que el dueño necesita saber sin abrir la tabla completa.
    monthly_payment: Decimal
    paid_principal: Decimal


class LoanPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    loan_id: str
    date: date_type
    amount: Decimal
    principal_part: Decimal
    interest_part: Decimal
    financial_account_id: str
    created_at: datetime
