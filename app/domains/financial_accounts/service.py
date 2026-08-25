from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.financial_account import FINANCIAL_ACCOUNT_TYPES, FinancialAccount, is_liability
from app.services.accounting.engine import _quantize
from app.services.accounting.coa import ledger_code_for
from app.services.accounting.rules import opening_balance_entry


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
) -> FinancialAccount:
    if account_type not in FINANCIAL_ACCOUNT_TYPES:
        raise ValueError("Tipo de cuenta inválido.")
    opening = _quantize(opening_balance)
    if opening < 0:
        raise ValueError("El saldo inicial no puede ser negativo.")

    account = FinancialAccount(
        organization_id=organization_id,
        name=name.strip(),
        type=account_type,
        opening_balance=opening,
        current_balance=opening,
        institution=institution,
        last_four=last_four,
        credit_limit=credit_limit if is_liability(account_type) else None,
    )
    db.add(account)
    db.flush()

    if opening > 0:
        opening_balance_entry(
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
    return account
