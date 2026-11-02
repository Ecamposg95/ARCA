from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FiscalEntityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tax_id: str | None = Field(default=None, max_length=13)
    regime: str | None = Field(default=None, max_length=80)
    sort_order: int = Field(default=0, ge=0)


class FiscalEntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    tax_id: str | None = Field(default=None, max_length=13)
    regime: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class FiscalEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tax_id: str | None
    regime: str | None
    active: bool
    sort_order: int
    created_at: datetime
