from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ExpenseCreate(BaseModel):
    date: date_type
    vendor_id: str | None = None
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0, allow_inf_nan=False)  # TOTAL con impuesto
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    category_id: str
    project_id: str | None = None
    # Retenciones al proveedor. Se capturan; ARCA sugiere pero no impone.
    retention_isr: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    retention_iva: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    financial_account_id: str | None = None
    payment_method: str | None = Field(default=None, max_length=30)
    reference: str | None = Field(default=None, max_length=100)
    status: Literal["PENDING", "PAID"] = "PENDING"
    notes: str | None = Field(default=None, max_length=1000)


class ExpensePay(BaseModel):
    financial_account_id: str | None = None
    date: date_type | None = None


class ExpenseCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date_type
    vendor_id: str | None
    description: str
    amount: Decimal
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    retention_isr: Decimal
    retention_iva: Decimal
    category_id: str
    project_id: str | None = None
    financial_account_id: str | None
    payment_method: str | None
    reference: str | None
    status: str
    notes: str | None
    paid_at: datetime | None
    created_at: datetime

    @computed_field
    @property
    def deductibility_warning(self) -> str | None:
        """Aviso fiscal calculado en el backend: la UI sólo lo muestra."""
        from app.services.deductibility import cash_warning

        return cash_warning(self.amount, self.payment_method)
