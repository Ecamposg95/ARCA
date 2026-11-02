from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page

ImportKind = Literal["TORONJA", "INCOMES", "EXPENSES", "CASH"]

# Campos a los que se puede mapear una columna del archivo genérico.
MAPPING_FIELDS = (
    "fecha",
    "concepto",
    "monto",
    "ingreso",
    "egreso",
    "categoria",
    "cuenta",
    "unidad",
    "contribuyente",
    "referencia",
    "forma_pago",
)
DEFAULT_FIELDS = (
    "category_id",
    "income_category_id",
    "expense_category_id",
    "financial_account_id",
    "business_unit_id",
)


class ImportRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    row_number: int
    external_id: str | None
    payload: dict[str, Any]
    status: str
    message: str | None
    result_type: str | None
    result_id: str | None


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    filename: str
    status: str
    mapping: dict[str, Any]
    options: dict[str, Any]
    summary: dict[str, Any]
    confirmed_at: datetime | None
    created_at: datetime


class ImportBatchDetail(ImportBatchRead):
    rows: Page[ImportRowRead]


class MappingRequest(BaseModel):
    mapping: dict[str, str | None] = Field(default_factory=dict)
    defaults: dict[str, str | None] = Field(default_factory=dict)


class ToronjaSettings(BaseModel):
    bank_account_id: str | None = None
    processor_account_id: str | None = None
    receivable_customer_id: str | None = None
    income_category_id: str | None = None


class ImportSettingsRead(BaseModel):
    toronja: ToronjaSettings = Field(default_factory=ToronjaSettings)


class ImportSettingsUpdate(BaseModel):
    toronja: ToronjaSettings | None = None
