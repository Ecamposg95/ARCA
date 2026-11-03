from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

OpeningStatus = Literal["PROVISIONAL", "CONFIRMED"]


class OpeningSettingsUpdate(BaseModel):
    """Fecha de corte y estado general de la apertura. Sólo lo enviado cambia."""

    opening_date: date_type | None = None
    opening_status: OpeningStatus | None = None
    reason: str | None = Field(default=None, max_length=500)


class AccountOpeningAdjustment(BaseModel):
    # Saldo al corte en la naturaleza de la cuenta: en una tarjeta, lo que se debía.
    target_opening_balance: Decimal = Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    reason: str = Field(min_length=5, max_length=500)
    status: OpeningStatus | None = None
    # De dónde sale la cifra ("Estado de cuenta oct-2026", "Pendiente"). Null la deja como está.
    note: str | None = Field(default=None, max_length=255)


class OpeningAccountRow(BaseModel):
    id: str
    name: str
    type: str
    active: bool
    is_liability: bool
    opening_balance: Decimal
    current_balance: Decimal
    opening_status: OpeningStatus
    opening_note: str | None


class OpeningLoanRow(BaseModel):
    id: str
    lender: str
    description: str
    principal: Decimal
    outstanding: Decimal
    start_date: date_type


class OpeningAssetRow(BaseModel):
    id: str
    name: str
    cost: Decimal
    accumulated_depreciation: Decimal
    book_value: Decimal
    acquisition_date: date_type


class OpeningOtherRow(BaseModel):
    account_id: str
    code: str
    name: str
    type: str
    amount: Decimal


class OpeningCandidate(BaseModel):
    account_id: str
    code: str
    name: str
    type: str


class OpeningSummary(BaseModel):
    organization_id: str
    opening_date: date_type | None
    opening_status: OpeningStatus | None
    # Saldo acreedor de 3901: lo capturado que aún no tiene documento.
    bridge_balance: Decimal
    accounts: list[OpeningAccountRow]
    loans: list[OpeningLoanRow]
    fixed_assets: list[OpeningAssetRow]
    other_entry_id: str | None
    other_entry_folio: str | None
    other_balancing_code: str | None
    others: list[OpeningOtherRow]
    other_candidates: list[OpeningCandidate]
