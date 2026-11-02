"""Traspasos entre instrumentos propios.

Un traspaso son dos movimientos (sale de una cuenta, entra a otra) y una
póliza neutra entre sus cuentas espejo. Lo usan el router de movimientos,
las liquidaciones de procesadores y la entrega del corte de caja.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.financial_account import FinancialAccount, is_liability
from app.models.transaction import FinancialTransaction
from app.services.accounting.coa import ledger_code_for
from app.services.accounting.rules import transfer_entry
from app.services.dimensions import tag_entry, validate_dimensions
from app.services.reversals import reverse_operation
from app.services.transactions import get_locked_account, record_transaction

TRANSFER_SOURCE = "transfer"


@dataclass(frozen=True)
class Transfer:
    group_id: str
    origin: FinancialAccount
    destination: FinancialAccount
    outgoing: FinancialTransaction
    incoming: FinancialTransaction
    entry: JournalEntry


def create_transfer(
    db: Session,
    organization_id: str,
    *,
    from_account_id: str,
    to_account_id: str,
    amount: Decimal,
    date: date_type,
    description: str | None = None,
    user_id: str | None = None,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
) -> Transfer:
    """Mueve `amount` de una cuenta a otra. No hace commit.

    Los dos movimientos y la póliza comparten `transfer_group_id` como
    `source_id`, así `reverse_operation("transfer", group_id)` deshace el
    traspaso completo.
    """
    if from_account_id == to_account_id:
        raise ValueError("Elige dos cuentas distintas para el traspaso.")

    origin = get_locked_account(db, organization_id, from_account_id)
    destination = get_locked_account(db, organization_id, to_account_id)
    validate_dimensions(db, organization_id, business_unit_id, fiscal_entity_id)
    if is_liability(destination.type):
        default_description = f"Pago de {destination.name} desde {origin.name}"
    else:
        default_description = f"Traspaso de {origin.name} a {destination.name}"
    description = description or default_description
    group_id = str(uuid4())

    outgoing = record_transaction(
        db,
        organization_id=organization_id,
        financial_account_id=origin.id,
        transaction_type="TRANSFER_OUT",
        amount=amount,
        date=date,
        description=description,
        source_type=TRANSFER_SOURCE,
        source_id=group_id,
        transfer_group_id=group_id,
        created_by=user_id,
    )
    incoming = record_transaction(
        db,
        organization_id=organization_id,
        financial_account_id=destination.id,
        transaction_type="TRANSFER_IN",
        amount=amount,
        date=date,
        description=description,
        source_type=TRANSFER_SOURCE,
        source_id=group_id,
        transfer_group_id=group_id,
        created_by=user_id,
    )
    entry = transfer_entry(
        db,
        organization_id,
        description=description,
        amount=amount,
        date=date,
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
    tag_entry(entry, business_unit_id or same_unit, fiscal_entity_id)
    return Transfer(group_id, origin, destination, outgoing, incoming, entry)


def reverse_transfer(
    db: Session,
    organization_id: str,
    group_id: str,
    *,
    description: str,
    date: date_type,
    user_id: str | None = None,
) -> dict:
    """Deshace un traspaso con la póliza espejo y los movimientos inversos. No hace commit."""
    return reverse_operation(
        db,
        organization_id,
        source_type=TRANSFER_SOURCE,
        source_id=group_id,
        description=description,
        date=date,
        user_id=user_id,
    )


def create_transfer_from_payload(db: Session, organization_id: str, payload, user_id: str) -> list[FinancialTransaction]:
    """El traspaso que captura una persona (o aprueba la bandeja): registra y
    confirma. Devuelve [salida, entrada]."""
    transfer = create_transfer(
        db,
        organization_id,
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        amount=payload.amount,
        date=payload.date,
        description=payload.description,
        user_id=user_id,
        business_unit_id=payload.business_unit_id,
        fiscal_entity_id=payload.fiscal_entity_id,
    )
    db.commit()
    db.refresh(transfer.outgoing)
    db.refresh(transfer.incoming)
    return [transfer.outgoing, transfer.incoming]
