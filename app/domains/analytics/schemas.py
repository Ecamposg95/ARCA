from __future__ import annotations

from datetime import date, datetime

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
