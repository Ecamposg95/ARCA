from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.transactions import service
from app.domains.transactions.listing import (
    TRANSACTION_HEADERS,
    TRANSACTION_MONEY_COLUMNS,
    TRANSACTION_STATUS_INDEX,
    TransactionFilters,
    filter_transactions,
    sorted_transactions,
    transaction_export_rows,
    transaction_list_filters,
)
from app.domains.transactions.schemas import TransferCreate
from app.models.organization import WRITE_ROLES
from app.models.financial_account import FinancialAccount
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.models.accounting import JournalEntry
from app.models.fiscal_entity import FiscalEntity
from app.services import approvals
from app.services.listing import check_export_size, export_response, money_total_row
from app.services.running_balance import running_balances

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    financial_account_id: str
    transaction_type: str
    amount: Decimal
    currency: str
    date: date_type
    description: str
    reference: str | None
    status: str
    payment_method: str | None
    source_type: str | None
    source_id: str | None
    created_at: datetime
    # Sólo se llena al filtrar por una cuenta: el acumulado entre bancos no significa nada.
    running_balance: Decimal | None = None
    # Unidad de la cuenta al registrar. La entidad viene de la póliza de la
    # operación (un movimiento no declara impuestos, su operación sí).
    business_unit_id: str | None = None
    business_unit_name: str | None = None
    fiscal_entity_id: str | None = None
    fiscal_entity_name: str | None = None


def _fill_fiscal_entities(db: Session, org_id: str, items: list[TransactionRead]) -> None:
    """Entidad fiscal de cada movimiento, vía la póliza de su operación, en una consulta."""
    keys = {key for item in items for key in (item.source_id,) if key}
    if not keys:
        return
    rows = (
        db.query(JournalEntry.source_id, FiscalEntity.id, FiscalEntity.name)
        .join(FiscalEntity, FiscalEntity.id == JournalEntry.fiscal_entity_id)
        .filter(JournalEntry.organization_id == org_id, JournalEntry.source_id.in_(keys))
        .all()
    )
    by_source = {source_id: (entity_id, name) for source_id, entity_id, name in rows}
    for item in items:
        match = by_source.get(item.source_id)
        if match:
            item.fiscal_entity_id, item.fiscal_entity_name = match


@router.get("")
def list_transactions(
    filters: TransactionFilters = Depends(transaction_list_filters),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = sorted_transactions(filter_transactions(db, org_id, filters))
    page = paginate(query, limit, offset, TransactionRead)
    _fill_fiscal_entities(db, org_id, page["items"])

    if filters.account_id:
        balances = running_balances(db, org_id, filters.account_id, [item.id for item in page["items"]])
        for item in page["items"]:
            item.running_balance = balances.get(item.id)
    return page


@router.get("/export")
def export_transactions(
    filters: TransactionFilters = Depends(transaction_list_filters),
    file_format: str = Query(default="xlsx", alias="format", pattern="^(xlsx|csv)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Los movimientos de la lista, con los mismos filtros, en Excel o CSV."""
    query = sorted_transactions(filter_transactions(db, org_id, filters))
    check_export_size(query)
    rows = transaction_export_rows(db, org_id, query)
    return export_response(
        rows=rows,
        total_row=money_total_row(
            rows,
            status_index=TRANSACTION_STATUS_INDEX,
            money_columns=TRANSACTION_MONEY_COLUMNS,
            width=len(TRANSACTION_HEADERS),
        ),
        file_format=file_format,
        prefix="movimientos",
        sheet_title="Movimientos",
        start=filters.start,
        end=filters.end,
        headers=TRANSACTION_HEADERS,
        money_columns=TRANSACTION_MONEY_COLUMNS,
    )


@router.post("/transfer", response_model=list[TransactionRead], status_code=201)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership=Depends(require_role(WRITE_ROLES)),
):
    waiting = approvals.gate(
        db,
        membership=membership,
        user=user,
        amount=payload.amount,
        kind="TRANSFER",
        payload=payload.model_dump(mode="json"),
        summary=_transfer_summary(db, org_id, payload),
    )
    if waiting is not None:
        return JSONResponse(status_code=202, content=approvals.pending_body(db, waiting))
    legs = service.create_transfer_from_payload(db, org_id, payload, user.id)
    return [TransactionRead.model_validate(leg) for leg in legs]


def _transfer_summary(db: Session, org_id: str, payload: TransferCreate) -> str:
    names = {
        account.id: account.name
        for account in db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == org_id,
            FinancialAccount.id.in_((payload.from_account_id, payload.to_account_id)),
        )
        .all()
    }
    origin = names.get(payload.from_account_id, "?")
    destination = names.get(payload.to_account_id, "?")
    return f"Traspaso de {approvals.money(payload.amount)} de {origin} a {destination}"
