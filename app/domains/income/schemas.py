from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IncomeCreate(BaseModel):
    date: date_type
    customer_id: str | None = None
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0, allow_inf_nan=False)  # TOTAL con impuesto
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    category_id: str
    project_id: str | None = None
    # Dimensiones del libro: la unidad se hereda de la cuenta si no viene;
    # la entidad fiscal nunca se infiere.
    business_unit_id: str | None = None
    fiscal_entity_id: str | None = None
    financial_account_id: str | None = None
    # Cómo cobraste y con qué referencia: viven en el movimiento, no en el
    # ingreso. Con tarjeta y sin cuenta explícita, el dinero cae al procesador
    # de pagos de la empresa; la importación de Toronja deja aquí su rastro.
    payment_method: str | None = Field(default=None, max_length=30)
    reference: str | None = Field(default=None, max_length=100)
    status: Literal["PENDING", "PAID"] = "PENDING"
    notes: str | None = Field(default=None, max_length=1000)


class IncomeUpdate(BaseModel):
    """Edición parcial. Pendiente: casi todo es corregible; cobrado o cancelado,
    sólo el proyecto (el resto exige reverso). Cada cambio queda en el historial."""

    date: date_type | None = None
    customer_id: str | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    category_id: str | None = None
    project_id: str | None = None
    financial_account_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)


class IncomePay(BaseModel):
    financial_account_id: str | None = None
    date: date_type | None = None
    payment_method: str | None = Field(default=None, max_length=30)


class IncomeCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class IncomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date_type
    customer_id: str | None
    description: str
    amount: Decimal
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    category_id: str
    project_id: str | None = None
    business_unit_id: str | None = None
    business_unit_name: str | None = None
    fiscal_entity_id: str | None = None
    fiscal_entity_name: str | None = None
    financial_account_id: str | None
    status: str
    notes: str | None
    paid_at: datetime | None
    created_at: datetime
