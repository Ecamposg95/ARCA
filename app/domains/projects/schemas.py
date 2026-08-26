from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=30)
    customer_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    budget: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    start_date: date_type | None = None
    end_date: date_type | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str | None
    customer_id: str | None
    description: str | None
    budget: Decimal | None
    start_date: date_type | None
    end_date: date_type | None
    status: str
    created_at: datetime
