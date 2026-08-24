"""Catálogo contable inicial (task pack §17), sembrado por organización.

El emprendedor nunca configura esto; ARCA lo crea al dar de alta la empresa.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.accounting import Account

# Códigos usados por el motor de reglas (app/services/accounting/rules.py)
CODE_CASH_BANK = "1100"
CODE_ACCOUNTS_RECEIVABLE = "1200"
CODE_OTHER_ASSETS = "1300"
CODE_ACCOUNTS_PAYABLE = "2100"
CODE_CAPITAL = "3100"
CODE_RETAINED_EARNINGS = "3200"
CODE_SALES = "4100"
CODE_SERVICES = "4200"
CODE_OPERATING_EXPENSES = "5100"
CODE_OTHER_EXPENSES = "5700"

# (code, name, type, parent_code)
DEFAULT_CHART = (
    ("1000", "Activo", "ASSET", None),
    ("1100", "Caja y Bancos", "ASSET", "1000"),
    ("1200", "Cuentas por Cobrar", "ASSET", "1000"),
    ("1300", "Otros Activos", "ASSET", "1000"),
    ("2000", "Pasivo", "LIABILITY", None),
    ("2100", "Cuentas por Pagar", "LIABILITY", "2000"),
    ("3000", "Capital", "EQUITY", None),
    ("3100", "Capital", "EQUITY", "3000"),
    ("3200", "Resultados Acumulados", "EQUITY", "3000"),
    ("4000", "Ingresos", "REVENUE", None),
    ("4100", "Ventas", "REVENUE", "4000"),
    ("4200", "Servicios", "REVENUE", "4000"),
    ("5000", "Gastos", "EXPENSE", None),
    ("5100", "Gastos Operativos", "EXPENSE", "5000"),
    ("5200", "Nómina", "EXPENSE", "5000"),
    ("5300", "Renta", "EXPENSE", "5000"),
    ("5400", "Software", "EXPENSE", "5000"),
    ("5500", "Marketing", "EXPENSE", "5000"),
    ("5600", "Transporte", "EXPENSE", "5000"),
    ("5700", "Otros Gastos", "EXPENSE", "5000"),
)


def seed_chart_of_accounts(db: Session, organization_id: str) -> None:
    """Crea el catálogo §17. Idempotente por (org, code). No hace commit."""
    existing_codes = {
        code
        for (code,) in db.query(Account.code).filter(Account.organization_id == organization_id).all()
    }
    created: dict[str, Account] = {}
    for code, name, account_type, parent_code in DEFAULT_CHART:
        if code in existing_codes:
            continue
        parent = created.get(parent_code) if parent_code else None
        account = Account(
            organization_id=organization_id,
            code=code,
            name=name,
            type=account_type,
            parent_id=parent.id if parent else None,
            system=True,
        )
        db.add(account)
        db.flush()
        created[code] = account


def get_account_by_code(db: Session, organization_id: str, code: str) -> Account:
    account = (
        db.query(Account)
        .filter(
            Account.organization_id == organization_id,
            Account.code == code,
            Account.active.is_(True),
        )
        .first()
    )
    if account is None:
        raise ValueError(f"No existe la cuenta contable {code} en esta organización.")
    return account
