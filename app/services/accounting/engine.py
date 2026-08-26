"""Motor de asientos contables — ÚNICO punto de escritura al ledger.

Nunca crear JournalEntry/JournalEntryLine fuera de post_journal_entry():
es el punto donde se hace cumplir la partida doble.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.accounting import (
    Account,
    DEBIT_NORMAL_TYPES,
    JournalEntry,
    JournalEntryLine,
)
from app.services.accounting.coa import get_account_by_code
from app.services.accounting.folios import next_folio

logger = logging.getLogger("arca.accounting")

TWO_PLACES = Decimal("0.01")


class AccountingError(ValueError):
    """Regla contable violada. El mensaje es apto para mostrarse al usuario."""


class UnbalancedEntryError(AccountingError):
    pass


@dataclass(frozen=True)
class LineSpec:
    """Línea de asiento por código de cuenta. debit XOR credit > 0."""

    account_code: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str | None = None


def _quantize(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(TWO_PLACES)


class ClosedPeriodError(AccountingError):
    """Se intentó tocar un mes ya cerrado."""


def _assert_period_open(db: Session, organization_id: str, date: date_type) -> None:
    from app.models.period import PeriodLock

    lock = (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.year == date.year,
            PeriodLock.month == date.month,
            PeriodLock.reopened_at.is_(None),
        )
        .first()
    )
    if lock is not None:
        raise ClosedPeriodError(
            f"{date.strftime('%m/%Y')} está cerrado. Reábrelo si necesitas corregir algo."
        )


def post_journal_entry(
    db: Session,
    organization_id: str,
    date: date_type,
    description: str,
    lines: list[LineSpec],
    source_type: str | None = None,
    source_id: str | None = None,
    reference: str | None = None,
    created_by: str | None = None,
    kind: str = "DIARIO",
) -> JournalEntry:
    """Valida y persiste una póliza balanceada. No hace commit (transacción del caller).

    `kind` (INGRESO/EGRESO/DIARIO) lo declara cada regla de negocio y define la
    serie del folio; no se infiere de las líneas.
    """
    if len(lines) < 2:
        raise AccountingError("Un asiento contable requiere al menos dos líneas.")

    # El candado se valida AQUÍ, en el único punto por donde pasa toda póliza:
    # ponerlo en cada router dejaría puertas abiertas por olvido.
    _assert_period_open(db, organization_id, date)

    total_debit = Decimal("0")
    total_credit = Decimal("0")
    resolved: list[tuple[Account, Decimal, Decimal, str | None]] = []

    for line in lines:
        debit = _quantize(line.debit)
        credit = _quantize(line.credit)
        if debit < 0 or credit < 0:
            raise AccountingError("Los montos contables no pueden ser negativos.")
        if (debit > 0) == (credit > 0):
            raise AccountingError("Cada línea debe tener cargo o abono, no ambos ni ninguno.")
        account = get_account_by_code(db, organization_id, line.account_code)
        resolved.append((account, debit, credit, line.description))
        total_debit += debit
        total_credit += credit

    if total_debit != total_credit:
        logger.error(
            "asiento desbalanceado rechazado org=%s debit=%s credit=%s desc=%s",
            organization_id,
            total_debit,
            total_credit,
            description,
        )
        raise UnbalancedEntryError("El asiento no está balanceado: cargos y abonos deben ser iguales.")

    entry = JournalEntry(
        organization_id=organization_id,
        folio=next_folio(db, organization_id, kind, date),
        kind=kind,
        date=date,
        description=description,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        created_by=created_by,
    )
    db.add(entry)
    db.flush()

    for account, debit, credit, line_description in resolved:
        db.add(
            JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=account.id,
                debit=debit,
                credit=credit,
                description=line_description,
            )
        )
    db.flush()
    event_bus.publish("journal_entry.created", {"journal_entry_id": entry.id, "organization_id": organization_id})
    return entry


def account_type_balance(
    db: Session,
    organization_id: str,
    account_type: str,
    start: date_type | None = None,
    end: date_type | None = None,
) -> Decimal:
    """Saldo neto (naturaleza normal) de todas las cuentas de un tipo, desde el ledger."""
    query = (
        db.query(
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            Account.type == account_type,
        )
    )
    if start is not None:
        query = query.filter(JournalEntry.date >= start)
    if end is not None:
        query = query.filter(JournalEntry.date <= end)
    debit, credit = query.one()
    debit = Decimal(debit or 0)
    credit = Decimal(credit or 0)
    if account_type in DEBIT_NORMAL_TYPES:
        return debit - credit
    return credit - debit


def trial_balance(db: Session, organization_id: str, as_of: date_type | None = None) -> list[dict]:
    """Balanza de comprobación: una fila por cuenta con movimientos."""
    query = (
        db.query(
            Account.code,
            Account.name,
            Account.type,
            func.coalesce(func.sum(JournalEntryLine.debit), 0).label("debit"),
            func.coalesce(func.sum(JournalEntryLine.credit), 0).label("credit"),
        )
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(
            Account.organization_id == organization_id,
            JournalEntry.status == "POSTED",
        )
        .group_by(Account.code, Account.name, Account.type)
        .order_by(Account.code)
    )
    if as_of is not None:
        query = query.filter(JournalEntry.date <= as_of)
    rows = []
    for code, name, account_type, debit, credit in query.all():
        debit = Decimal(debit or 0)
        credit = Decimal(credit or 0)
        if account_type in DEBIT_NORMAL_TYPES:
            balance = debit - credit
        else:
            balance = credit - debit
        rows.append(
            {
                "code": code,
                "name": name,
                "type": account_type,
                "debit": debit,
                "credit": credit,
                "balance": balance,
            }
        )
    return rows
