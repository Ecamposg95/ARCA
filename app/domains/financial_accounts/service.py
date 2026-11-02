from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.financial_account import FINANCIAL_ACCOUNT_TYPES, FinancialAccount, is_liability
from app.services.accounting.engine import _quantize
from app.services.accounting.coa import ledger_code_for
from app.services.accounting.rules import opening_balance_entry
from app.services.dimensions import tag_entry, validate_dimensions


def create_financial_account(
    db: Session,
    organization_id: str,
    name: str,
    account_type: str,
    opening_balance: Decimal = Decimal("0"),
    institution: str | None = None,
    last_four: str | None = None,
    credit_limit=None,
    created_by: str | None = None,
    business_unit_id: str | None = None,
    fee_rate: Decimal | None = None,
    settlement_days: int | None = None,
    settlement_account_id: str | None = None,
) -> FinancialAccount:
    if account_type not in FINANCIAL_ACCOUNT_TYPES:
        raise ValueError("Tipo de cuenta inválido.")
    opening = _quantize(opening_balance)
    if opening < 0:
        raise ValueError("El saldo inicial no puede ser negativo.")
    validate_dimensions(db, organization_id, business_unit_id, None)
    is_processor = account_type == "PROCESSOR"
    if is_processor and settlement_account_id:
        validate_settlement_account(db, organization_id, settlement_account_id)

    account = FinancialAccount(
        organization_id=organization_id,
        name=name.strip(),
        type=account_type,
        opening_balance=opening,
        current_balance=opening,
        institution=institution,
        last_four=last_four,
        credit_limit=credit_limit if is_liability(account_type) else None,
        business_unit_id=business_unit_id,
        fee_rate=fee_rate if is_processor else None,
        settlement_days=settlement_days if is_processor else None,
        settlement_account_id=settlement_account_id if is_processor else None,
    )
    db.add(account)
    db.flush()

    if opening > 0:
        entry = opening_balance_entry(
            db,
            organization_id,
            account_name=account.name,
            amount=opening,
            date=date.today(),
            source_id=account.id,
            created_by=created_by,
            account_code=ledger_code_for(account_type),
            liability=is_liability(account_type),
        )
        # El saldo inicial de la caja de Morelos es activo de Morelos.
        tag_entry(entry, business_unit_id, None)
    return account


def validate_settlement_account(db: Session, organization_id: str, bank_account_id: str) -> FinancialAccount:
    """El banco donde liquida un procesador: una cuenta BANK activa de la misma empresa."""
    bank = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == bank_account_id,
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if bank is None or not bank.active:
        raise ValueError("El banco donde liquida no existe.")
    if bank.type != "BANK":
        raise ValueError("Un procesador liquida a una cuenta de banco.")
    return bank
