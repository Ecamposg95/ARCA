"""Historial de cambios (HU-09). Sólo lectura: la bitácora es append-only."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.history import service
from app.models.change_log import CHANGE_ACTIONS
from app.security.deps import get_current_org_id

router = APIRouter(tags=["history"])

ENTITY_PATTERN = "^(expense|income|payable|receivable|transfer|financial_account|category|contact|proposal|opening_balance)$"
ACTION_PATTERN = "^(" + "|".join(CHANGE_ACTIONS) + ")$"


@router.get("/history")
def list_history(
    entity_type: str | None = Query(default=None, pattern=ENTITY_PATTERN),
    entity_id: str | None = Query(default=None, max_length=36),
    user_id: str | None = Query(default=None, max_length=36),
    action: str | None = Query(default=None, pattern=ACTION_PATTERN),
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="La fecha inicial no puede ser posterior a la final.")
    return service.history_page(
        db,
        org_id,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


def _entity_history_route(path: str, entity_type: str):
    def handler(
        entity_id: str,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
    ):
        return service.history_page(
            db, org_id, entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset
        )

    handler.__name__ = f"history_of_{entity_type}"
    router.add_api_route(f"{path}/{{entity_id}}/history", handler, methods=["GET"])


# Atajos por recurso: el mismo historial, ya filtrado.
for _path, _entity_type in (
    ("/expenses", "expense"),
    ("/income", "income"),
    ("/payables", "payable"),
    ("/receivables", "receivable"),
    ("/accounts", "financial_account"),
    # La apertura general (corte, estado, cuentas sin módulo) cuelga de la empresa.
    ("/opening", "opening_balance"),
):
    _entity_history_route(_path, _entity_type)
