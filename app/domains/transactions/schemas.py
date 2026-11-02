from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


class TransferCreate(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    date: date_type
    description: str | None = Field(default=None, max_length=500)
    # Dimensiones de la póliza del traspaso. Cada pierna del movimiento lleva
    # la unidad de su propia cuenta, venga lo que venga aquí.
    business_unit_id: str | None = None
    fiscal_entity_id: str | None = None
