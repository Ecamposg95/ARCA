from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BusinessUnitKind = Literal["MATRIZ", "TOMA_MUESTRA", "UNIDAD_MOVIL", "CANAL", "OTRA"]


class BusinessUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=12)
    kind: BusinessUnitKind = "OTRA"
    opened_on: date_type | None = None
    aliases: list[str] = Field(default_factory=list, max_length=50)
    sort_order: int = Field(default=0, ge=0)


class BusinessUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=12)
    kind: BusinessUnitKind | None = None
    opened_on: date_type | None = None
    aliases: list[str] | None = Field(default=None, max_length=50)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class BusinessUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    kind: str
    active: bool
    opened_on: date_type | None
    aliases: list[str]
    sort_order: int
    # Cuántas cuentas de dinero pertenecen a la unidad; lo llena el router.
    accounts_count: int = 0
    created_at: datetime
