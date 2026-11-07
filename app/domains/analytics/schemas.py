from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class HistoricalLoadItem(BaseModel):
    family: str
    source: str
    period_from: date
    period_to: date
    rows: int


class HistoricalLoadReport(BaseModel):
    loads: list[HistoricalLoadItem]
    unresolved_units: list[str]
    unresolved_entities: list[str]
    dry_run: bool


class HistoricalLoadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    period_from: date
    period_to: date
    rows: int
    loaded_by: str | None
    loaded_at: datetime
    notes: str | None


class SeriesPoint(BaseModel):
    period: date
    value: Decimal
    origin: Literal["historical", "live"]
    partial: bool


class ComparePoint(BaseModel):
    period: date
    value: Decimal
    origin: Literal["historical", "live"]


class TargetPoint(BaseModel):
    period: date
    value: Decimal


class AnalyticsSeries(BaseModel):
    points: list[SeriesPoint]
    previous: list[ComparePoint] | None
    target: list[TargetPoint] | None
    opening_date: date | None
    historical_available: bool
    historical_note: str | None
