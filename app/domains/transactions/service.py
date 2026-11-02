"""Traspaso entre cuentas de dinero: dos movimientos y una póliza.

Vive aquí y no en el router porque la bandeja de autorización lo ejecuta al
aprobar: un traspaso que alcanza el umbral espera igual que un gasto.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.financial_account import is_liability
from app.models.transaction import FinancialTransaction
from app.services.accounting.coa import ledger_code_for
from app.services.accounting.rules import transfer_entry
from app.services.dimensions import tag_entry, validate_dimensions
from app.services.transactions import get_locked_account, record_transaction


def create_transfer(db: Session, org_id: str, payload, user_id: str) -> list[FinancialTransaction]:
    """Devuelve [salida, entrada] ya confirmados."""
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
        created_by=user_id,
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
        created_by=user_id,
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
        created_by=user_id,
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
    return [outgoing, incoming]
