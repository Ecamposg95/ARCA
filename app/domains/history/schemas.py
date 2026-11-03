from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FieldChange(BaseModel):
    field: str
    label: str  # nombre amigable en español ("Monto", "Categoría")
    kind: str  # money | date | text | status | bool | rate | ref
    old: Any = None
    new: Any = None
    # Para referencias (categoría, cuenta, proveedor…): el nombre, resuelto en el backend.
    old_display: str | None = None
    new_display: str | None = None


class HistoryEvent(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    entity_label: str | None = None
    action: str
    source: str
    reason: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    created_at: datetime
    changes: list[FieldChange]
