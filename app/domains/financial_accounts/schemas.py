from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.financial_account import AVAILABLE_ACCOUNT_TYPES, LIABILITY_ACCOUNT_TYPES

FinancialAccountType = Literal["CASH", "BANK", "CREDIT_CARD", "PROCESSOR", "OTHER"]


class FinancialAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: FinancialAccountType
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    institution: str | None = Field(default=None, max_length=100)
    last_four: str | None = Field(default=None, max_length=4)
    credit_limit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    # A qué unidad pertenece la caja (la caja de Morelos). Opcional.
    business_unit_id: str | None = None
    # Sólo procesadores: comisión pactada (0.035 = 3.5 %), días en que
    # deposita y banco donde liquida.
    fee_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    settlement_days: int | None = Field(default=None, ge=0, le=365)
    settlement_account_id: str | None = None


class FinancialAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    institution: str | None = Field(default=None, max_length=100)
    last_four: str | None = Field(default=None, max_length=4)
    active: bool | None = None
    business_unit_id: str | None = None
    fee_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    settlement_days: int | None = Field(default=None, ge=0, le=365)
    settlement_account_id: str | None = None


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
    business_unit_id: str | None = None
    business_unit_name: str | None = None
    fee_rate: Decimal | None = None
    settlement_days: int | None = None
    settlement_account_id: str | None = None
    # Apertura ajustable: PROVISIONAL / CONFIRMED (null = nunca revisada) y la fuente de la cifra.
    opening_status: str | None = None
    opening_note: str | None = None
    created_at: datetime

    @computed_field
    @property
    def is_liability(self) -> bool:
        """Una tarjeta registra deuda: su saldo es lo que debes, no lo que tienes."""
        return self.type in LIABILITY_ACCOUNT_TYPES

    @computed_field
    @property
    def available(self) -> bool:
        """Si el saldo cuenta como disponible. Un procesador no: está en tránsito al banco."""
        return self.type in AVAILABLE_ACCOUNT_TYPES

    @computed_field
    @property
    def available_credit(self) -> Decimal | None:
        if self.credit_limit is None or not self.is_liability:
            return None
        return self.credit_limit - self.current_balance


# --- Liquidaciones de procesadores ---


class SettlementCreate(BaseModel):
    date: date_type
    gross_amount: Decimal = Field(gt=0, allow_inf_nan=False)  # lo que cobró el procesador
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)  # su comisión
    # Si no viene, el banco configurado en el procesador.
    bank_account_id: str | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class SettlementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    processor_account_id: str
    bank_account_id: str
    date: date_type
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    reference: str | None
    notes: str | None
    status: str
    transfer_group_id: str
    expense_id: str | None
    created_by: str | None
    cancelled_at: datetime | None
    created_at: datetime
