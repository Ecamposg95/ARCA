from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

CATEGORY_PATTERN = "^(EQUIPO_COMPUTO|MOBILIARIO|VEHICULOS|MAQUINARIA|EDIFICIOS|OTRO)$"


class FixedAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="OTRO", pattern=CATEGORY_PATTERN)
    acquisition_date: date_type
    # Costo SIN impuesto: el IVA se acredita, no forma parte del activo.
    cost: Decimal = Field(gt=0, allow_inf_nan=False)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    salvage_value: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    useful_life_months: int = Field(gt=0, le=1200)
    financial_account_id: str | None = None
    vendor_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)


class FixedAssetDispose(BaseModel):
    disposed_at: date_type | None = None


class DepreciationRun(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class FixedAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    acquisition_date: date_type
    cost: Decimal
    tax_amount: Decimal
    salvage_value: Decimal
    useful_life_months: int
    accumulated_depreciation: Decimal
    financial_account_id: str | None
    vendor_id: str | None
    status: str
    disposed_at: date_type | None
    notes: str | None
    created_at: datetime

    # Derivados: el dueño pregunta "¿cuánto vale hoy?", no "¿cuánto llevo depreciado?".
    book_value: Decimal
    monthly_depreciation: Decimal
    months_remaining: int
