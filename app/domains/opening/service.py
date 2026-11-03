"""Apertura provisional y ajustable a la fecha de corte.

La empresa llega a ONE Finance un día (la fecha de corte) sabiendo sólo algunos
de sus saldos. Lo demás se captura en cero o con una cifra provisional y se
corrige cuando llega el estado de cuenta, sin tocar lo registrado después:

- Cuentas de dinero (cajas, bancos, procesador, tarjetas): cada corrección es
  un movimiento de ajuste vía `record_transaction` y una póliza contra la
  cuenta puente 3901 (`rules.opening_adjustment_entry`), ambos fechados en el
  corte. `opening_balance` pasa a la cifra nueva; `current_balance` se mueve
  sólo por la diferencia.
- Cuentas sin módulo (depósitos, anticipos, deudores…): la póliza de apertura
  viva se revierte y se asienta la nueva en la misma transacción
  (`rules.reverse_manual_entry` + `rules.opening_entry`).

Nada se borra ni se edita: cada corrección deja su póliza, su movimiento y su
renglón en la bitácora con el motivo. Ninguna función hace commit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.financial_account import FinancialAccount, is_liability
from app.models.fixed_asset import FixedAsset
from app.models.loan import Loan
from app.models.organization import OPENING_PROVISIONAL, OPENING_STATUSES, Organization
from app.models.transaction import OPENING_ADJUSTMENT_SOURCE, FinancialTransaction
from app.services.accounting.coa import CODE_OPENING_BRIDGE, ledger_code_for
from app.services.accounting.engine import (
    TWO_PLACES,
    ClosedPeriodError,
    assert_period_open,
    lock_organization,
)
from app.services.accounting.rules import (
    BALANCE_SHEET_TYPES,
    MODULE_CONTROLLED_CODES,
    OPENING_BALANCING_CODES,
    OpeningLine,
    live_opening_entry,
    opening_adjustment_entry,
    opening_entry,
    reverse_manual_entry,
)
from app.services.change_log import record_change, snapshot
from app.services.dimensions import tag_entry
from app.services.transactions import get_locked_account, record_transaction

# La bitácora de la apertura general (fecha de corte, estado y cuentas sin
# módulo) cuelga de la empresa: no hay otro registro que la represente.
OPENING_ENTITY = "opening_balance"
ACCOUNT_OPENING_FIELDS = ("opening_balance", "opening_status", "opening_note")
MIN_REASON = 5
BALANCING_DESCRIPTION = "Cuadre de la apertura"


class OpeningError(ValueError):
    """Regla de la apertura violada. Mensaje apto para el usuario (400)."""


def _org(db: Session, organization_id: str) -> Organization:
    return db.query(Organization).filter(Organization.id == organization_id).one()


def _reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if len(text) < MIN_REASON:
        raise OpeningError("Escribe el motivo del ajuste (al menos 5 letras): queda en el historial.")
    return text[:500]


def _status(status: str | None) -> str | None:
    if status is not None and status not in OPENING_STATUSES:
        raise OpeningError("El estado de la apertura es Provisional o Confirmada.")
    return status


def require_cutoff(organization: Organization) -> date_type:
    if organization.opening_date is None:
        raise OpeningError(
            "Primero fija la fecha de corte en Configuración › Apertura: los saldos de apertura van fechados ahí."
        )
    return organization.opening_date


def assert_cutoff_open(db: Session, organization_id: str, cutoff: date_type) -> None:
    """Un mes cerrado no acepta pólizas: lo decimos antes y en términos de la apertura."""
    try:
        assert_period_open(db, organization_id, cutoff)
    except ClosedPeriodError as error:
        raise OpeningError(
            f"El mes de la fecha de corte ({cutoff:%m/%Y}) está cerrado. Reábrelo en Contabilidad › Cierres "
            f"para registrar o corregir la apertura. ({error})"
        ) from error


def has_openings(db: Session, organization_id: str) -> bool:
    """¿Hay ya algo fechado en el corte? Entonces la fecha no se puede mover."""
    adjusted = (
        db.query(FinancialTransaction.id)
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.source_type == OPENING_ADJUSTMENT_SOURCE,
        )
        .first()
    )
    return adjusted is not None or live_opening_entry(db, organization_id) is not None


# --- Fecha de corte y estado general ---


def update_settings(
    db: Session,
    organization_id: str,
    *,
    changes: dict,
    user_id: str | None,
) -> Organization:
    """Fija la fecha de corte y/o el estado general. `changes` trae sólo lo enviado."""
    lock_organization(db, organization_id)
    organization = _org(db, organization_id)
    before = {"opening_date": organization.opening_date, "opening_status": organization.opening_status}

    if "opening_date" in changes:
        new_date = changes["opening_date"]
        if new_date is None:
            raise OpeningError("La fecha de corte no se puede quitar; cámbiala por otra si te equivocaste.")
        if new_date != organization.opening_date:
            if new_date > date_type.today():
                raise OpeningError("La fecha de corte no puede ser futura.")
            if organization.opening_date is not None and has_openings(db, organization_id):
                raise OpeningError(
                    f"Ya hay saldos de apertura fechados al {organization.opening_date:%d/%m/%Y}; "
                    "la fecha de corte ya no se puede mover."
                )
            assert_cutoff_open(db, organization_id, new_date)
            organization.opening_date = new_date
            if organization.opening_status is None:
                organization.opening_status = OPENING_PROVISIONAL

    if "opening_status" in changes:
        status = _status(changes["opening_status"])
        if status is None:
            raise OpeningError("El estado de la apertura es Provisional o Confirmada.")
        require_cutoff(organization)
        organization.opening_status = status

    after = {"opening_date": organization.opening_date, "opening_status": organization.opening_status}
    record_change(
        db,
        organization_id,
        organization,
        "UPDATE",
        user_id,
        before=before,
        after=after,
        reason=changes.get("reason"),
        entity_type=OPENING_ENTITY,
    )
    db.flush()
    return organization


# --- Cuentas de dinero ---


@dataclass
class AccountAdjustment:
    account: FinancialAccount
    difference: Decimal
    transaction_id: str | None
    entry_id: str | None


def adjust_account_opening(
    db: Session,
    organization_id: str,
    account_id: str,
    *,
    target: Decimal,
    reason: str,
    status: str | None = None,
    note: str | None = None,
    user_id: str | None = None,
) -> AccountAdjustment:
    """Lleva el saldo de apertura de una cuenta de dinero a `target`.

    La diferencia contra la apertura vigente (la original más los ajustes
    previos) entra como movimiento de ajuste y póliza contra 3901, fechados en
    el corte. Sin diferencia sólo cambian el estado y la nota. Respeta la
    naturaleza: en una tarjeta `target` es lo que se debía al corte.
    """
    organization = _org(db, organization_id)
    cutoff = require_cutoff(organization)
    reason = _reason(reason)
    status = _status(status)
    target = Decimal(target).quantize(TWO_PLACES)
    if target < 0:
        raise OpeningError("El saldo de apertura no puede ser negativo.")

    # Lock → refresh → re-check: dos ajustes simultáneos no calculan la misma diferencia.
    account = get_locked_account(db, organization_id, account_id)
    before = snapshot(account, ACCOUNT_OPENING_FIELDS)
    difference = target - Decimal(account.opening_balance or 0)

    transaction_id = entry_id = None
    if difference != 0:
        assert_cutoff_open(db, organization_id, cutoff)
        liability = is_liability(account.type)
        # Más activo (o menos deuda) es entrada; lo contrario, salida.
        inflow = (difference > 0) != liability
        source_id = str(uuid.uuid4())
        movement = record_transaction(
            db,
            organization_id=organization_id,
            financial_account_id=account.id,
            transaction_type="ADJUSTMENT_IN" if inflow else "ADJUSTMENT",
            amount=abs(difference),
            date=cutoff,
            description=f"Ajuste de apertura al {cutoff:%d/%m/%Y}: {reason}"[:500],
            source_type=OPENING_ADJUSTMENT_SOURCE,
            source_id=source_id,
            created_by=user_id,
            payment_method="OTRO",
        )
        entry = opening_adjustment_entry(
            db,
            organization_id,
            account_name=account.name,
            difference=difference,
            date=cutoff,
            source_id=source_id,
            account_code=ledger_code_for(account.type),
            liability=liability,
            created_by=user_id,
        )
        # El saldo de la caja de Morelos es activo de Morelos, también en la apertura.
        tag_entry(entry, account.business_unit_id, None)
        account.opening_balance = target
        transaction_id, entry_id = movement.id, entry.id

    if status is not None:
        account.opening_status = status
    elif account.opening_status is None:
        account.opening_status = OPENING_PROVISIONAL
    if note is not None:
        account.opening_note = note.strip()[:255] or None

    record_change(
        db,
        organization_id,
        account,
        "UPDATE",
        user_id,
        before=before,
        after=snapshot(account, ACCOUNT_OPENING_FIELDS),
        reason=reason,
    )
    db.flush()
    return AccountAdjustment(account, difference, transaction_id, entry_id)


# --- Cuentas sin módulo (póliza de apertura) ---


def opening_lines(db: Session, entry: JournalEntry | None) -> tuple[list[dict], str | None]:
    """Las cuentas de la apertura viva en su naturaleza, sin la línea de cuadre."""
    if entry is None:
        return [], None
    rows = (
        db.query(JournalEntryLine, Account)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(JournalEntryLine.journal_entry_id == entry.id)
        .all()
    )
    lines: list[dict] = []
    balancing_code = None
    for line, account in rows:
        if account.code in OPENING_BALANCING_CODES and line.description == BALANCING_DESCRIPTION:
            balancing_code = account.code
            continue
        debit, credit = Decimal(line.debit), Decimal(line.credit)
        amount = debit - credit if account.type == "ASSET" else credit - debit
        lines.append(
            {
                "account_id": account.id,
                "code": account.code,
                "name": account.name,
                "type": account.type,
                "amount": amount.quantize(TWO_PLACES),
            }
        )
    lines.sort(key=lambda item: item["code"])
    return lines, balancing_code


def _line_key(line: dict) -> str:
    return f"line:{line['code']} {line['name']}"


def replace_opening(
    db: Session,
    organization_id: str,
    *,
    lines: list[OpeningLine],
    reason: str,
    balancing_code: str = CODE_OPENING_BRIDGE,
    description: str | None = None,
    user_id: str | None = None,
) -> JournalEntry | None:
    """Corrige la apertura de las cuentas sin módulo en un solo paso.

    Si hay apertura viva se revierte (el reverso lleva su fecha) y se asienta la
    nueva en la fecha de corte, en la misma transacción. Todo en cero deja sólo
    el reverso. Si nada cambió no se asienta nada. Devuelve la apertura vigente.
    """
    lock_organization(db, organization_id)
    organization = _org(db, organization_id)
    cutoff = require_cutoff(organization)
    reason = _reason(reason)
    assert_cutoff_open(db, organization_id, cutoff)

    live = live_opening_entry(db, organization_id)
    old_lines, old_balancing = opening_lines(db, live)

    wanted_ids = {line.account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.query(Account)
        .filter(Account.organization_id == organization_id, Account.id.in_(wanted_ids or {""}))
        .all()
    }
    new_lines: list[dict] = []
    for line in lines:
        amount = Decimal(line.amount).quantize(TWO_PLACES)
        account = accounts.get(line.account_id)
        if account is None:
            raise LookupError("Esa cuenta no existe.")
        if amount != 0:
            new_lines.append({"code": account.code, "name": account.name, "amount": amount})

    old_map = {_line_key(line): line["amount"] for line in old_lines}
    new_map = {_line_key(line): line["amount"] for line in new_lines}
    unchanged = (
        live is not None
        and old_map == new_map
        and live.date == cutoff
        and (old_balancing or balancing_code) == balancing_code
    )
    if unchanged:
        return live
    if live is None and not new_lines:
        raise OpeningError("Captura el saldo de al menos una cuenta.")

    if live is not None:
        reverse_manual_entry(
            db,
            organization_id,
            live,
            date=live.date,
            description=f"Reverso de {live.folio} por ajuste de apertura: {reason}"[:500],
            created_by=user_id,
        )
    entry = None
    if new_lines:
        entry = opening_entry(
            db,
            organization_id,
            date=cutoff,
            lines=lines,
            balancing_code=balancing_code,
            description=description,
            created_by=user_id,
        )

    before = {key: amount for key, amount in old_map.items()}
    after = {key: amount for key, amount in new_map.items()}
    if old_balancing != balancing_code:
        before["balancing_code"] = old_balancing
        after["balancing_code"] = balancing_code if entry is not None else None
    record_change(
        db,
        organization_id,
        organization,
        "UPDATE",
        user_id,
        before=before,
        after=after,
        reason=reason,
        entity_type=OPENING_ENTITY,
    )
    db.flush()
    return entry


# --- Resumen para la pantalla de Apertura ---


def bridge_balance(db: Session, organization_id: str) -> Decimal:
    """Saldo acreedor de 3901: lo capturado al corte que todavía no se identifica."""
    total = (
        db.query(func.coalesce(func.sum(JournalEntryLine.credit - JournalEntryLine.debit), 0))
        .join(Account, Account.id == JournalEntryLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(
            Account.organization_id == organization_id,
            Account.code == CODE_OPENING_BRIDGE,
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
        )
        .scalar()
    )
    return Decimal(total or 0).quantize(TWO_PLACES)


def summary(db: Session, organization_id: str) -> dict:
    organization = _org(db, organization_id)
    money = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.organization_id == organization_id, FinancialAccount.deleted_at.is_(None))
        .order_by(FinancialAccount.created_at)
        .all()
    )
    loans = (
        db.query(Loan)
        .filter(Loan.organization_id == organization_id, Loan.status == "ACTIVE")
        .order_by(Loan.start_date)
        .all()
    )
    assets = (
        db.query(FixedAsset)
        .filter(FixedAsset.organization_id == organization_id, FixedAsset.status == "ACTIVE")
        .order_by(FixedAsset.acquisition_date)
        .all()
    )
    live = live_opening_entry(db, organization_id)
    others, balancing_code = opening_lines(db, live)
    candidates = (
        db.query(Account)
        .filter(
            Account.organization_id == organization_id,
            Account.active.is_(True),
            Account.parent_id.isnot(None),
            Account.type.in_(BALANCE_SHEET_TYPES),
            Account.code.notin_([*MODULE_CONTROLLED_CODES, CODE_OPENING_BRIDGE]),
        )
        .order_by(Account.code)
        .all()
    )
    return {
        "opening_date": organization.opening_date,
        "opening_status": organization.opening_status,
        "bridge_balance": bridge_balance(db, organization_id),
        "accounts": [
            {
                "id": account.id,
                "name": account.name,
                "type": account.type,
                "active": account.active,
                "is_liability": is_liability(account.type),
                "opening_balance": Decimal(account.opening_balance or 0).quantize(TWO_PLACES),
                "current_balance": Decimal(account.current_balance or 0).quantize(TWO_PLACES),
                "opening_status": account.opening_status or OPENING_PROVISIONAL,
                "opening_note": account.opening_note,
            }
            for account in money
        ],
        "loans": [
            {
                "id": loan.id,
                "lender": loan.lender,
                "description": loan.description,
                "principal": Decimal(loan.principal),
                "outstanding": Decimal(loan.outstanding),
                "start_date": loan.start_date,
            }
            for loan in loans
        ],
        "fixed_assets": [
            {
                "id": asset.id,
                "name": asset.name,
                "cost": Decimal(asset.cost),
                "accumulated_depreciation": Decimal(asset.accumulated_depreciation or 0).quantize(TWO_PLACES),
                "book_value": (Decimal(asset.cost) - Decimal(asset.accumulated_depreciation or 0)).quantize(TWO_PLACES),
                "acquisition_date": asset.acquisition_date,
            }
            for asset in assets
        ],
        "other_entry_id": live.id if live is not None else None,
        "other_entry_folio": live.folio if live is not None else None,
        "other_balancing_code": balancing_code,
        "others": others,
        "other_candidates": [
            {"account_id": account.id, "code": account.code, "name": account.name, "type": account.type}
            for account in candidates
        ],
    }
