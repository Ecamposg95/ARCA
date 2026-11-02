from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import WRITE_ROLES
from app.models.financial_account import is_liability
from app.models.transaction import FinancialTransaction
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.models.accounting import JournalEntry
from app.models.fiscal_entity import FiscalEntity
from app.services.accounting.rules import transfer_entry
from app.services.accounting.coa import ledger_code_for
from app.services.dimensions import tag_entry, transaction_filters, validate_dimensions
from app.services.running_balance import running_balances
from app.services.transactions import get_locked_account, record_transaction

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
    account_id: str | None = None,
    transaction_type: str | None = None,
    # Origen: "los cobros de ESTA factura". Ambos o ninguno — un source_id
    # suelto cruzaría tipos de entidad distintos.
    source_type: str | None = Query(default=None, max_length=50),
    source_id: str | None = Query(default=None, max_length=64),
    start: date_type | None = None,
    end: date_type | None = None,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(FinancialTransaction).filter(
        FinancialTransaction.organization_id == org_id,
        *transaction_filters(business_unit_id, fiscal_entity_id),
    )
    if account_id:
        query = query.filter(FinancialTransaction.financial_account_id == account_id)
    if transaction_type:
        query = query.filter(FinancialTransaction.transaction_type == transaction_type)
    if source_type:
        query = query.filter(FinancialTransaction.source_type == source_type)
    if source_id:
        query = query.filter(FinancialTransaction.source_id == source_id)
    if start:
        query = query.filter(FinancialTransaction.date >= start)
    if end:
        query = query.filter(FinancialTransaction.date <= end)
    query = query.order_by(
        FinancialTransaction.date.desc(),
        FinancialTransaction.created_at.desc(),
        FinancialTransaction.id.desc(),
    )
    page = paginate(query, limit, offset, TransactionRead)
    _fill_fiscal_entities(db, org_id, page["items"])

    if account_id:
        balances = running_balances(db, org_id, account_id, [item.id for item in page["items"]])
        for item in page["items"]:
            item.running_balance = balances.get(item.id)
    return page


@router.post("/transfer", response_model=list[TransactionRead], status_code=201)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    if payload.from_account_id == payload.to_account_id:
        raise ValueError("Elige dos cuentas distintas para el traspaso.")

    origin = get_locked_account(db, org_id, payload.from_account_id)
    destination = get_locked_account(db, org_id, payload.to_account_id)
    validate_dimensions(db, org_id, payload.business_unit_id, payload.fiscal_entity_id)
    if is_liability(destination.type):
        default_description = f"Pago de {destination.name} desde {origin.name}"
    else:
        default_description = f"Traspaso de {origin.name} a {destination.name}"
    description = payload.description or default_description
    group_id = str(uuid4())

    outgoing = record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=origin.id,
        transaction_type="TRANSFER_OUT",
        amount=payload.amount,
        date=payload.date,
        description=description,
        source_type="transfer",
        transfer_group_id=group_id,
        created_by=user.id,
    )
    incoming = record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=destination.id,
        transaction_type="TRANSFER_IN",
        amount=payload.amount,
        date=payload.date,
        description=description,
        source_type="transfer",
        transfer_group_id=group_id,
        created_by=user.id,
    )
    entry = transfer_entry(
        db,
        org_id,
        description=description,
        amount=payload.amount,
        date=payload.date,
        from_account_name=origin.name,
        to_account_name=destination.name,
        source_id=group_id,
        created_by=user.id,
        from_account_code=ledger_code_for(origin.type),
        to_account_code=ledger_code_for(destination.type),
    )
    # La póliza lleva la unidad indicada; si no viene y ambas cajas son de la
    # misma unidad, esa. Entre unidades distintas no es de ninguna.
    same_unit = origin.business_unit_id if origin.business_unit_id == destination.business_unit_id else None
    tag_entry(entry, payload.business_unit_id or same_unit, payload.fiscal_entity_id)
    db.commit()
    db.refresh(outgoing)
    db.refresh(incoming)
    return [TransactionRead.model_validate(outgoing), TransactionRead.model_validate(incoming)]
