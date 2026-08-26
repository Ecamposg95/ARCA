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
# IVA por flujo de efectivo: lo "pendiente" aún no se declara ante el SAT.
CODE_VAT_CREDITABLE_PAID = "1190"
CODE_VAT_CREDITABLE_PENDING = "1191"
CODE_VAT_CHARGED_COLLECTED = "2190"
CODE_VAT_CHARGED_PENDING = "2191"
CODE_ACCOUNTS_PAYABLE = "2100"
CODE_CREDIT_CARDS = "2200"
CODE_CAPITAL = "3100"
CODE_RETAINED_EARNINGS = "3200"
CODE_SALES = "4100"
CODE_SERVICES = "4200"
CODE_OPERATING_EXPENSES = "5100"
CODE_OTHER_EXPENSES = "5700"
# Patrimonio: lo que se compra para usar años, y lo que se debe a plazos.
CODE_FIXED_ASSETS = "1400"
CODE_ACCUMULATED_DEPRECIATION = "1490"  # contra-activo: naturaleza acreedora
CODE_DEPRECIATION_EXPENSE = "5800"
CODE_LOANS_PAYABLE = "2300"
# Retenciones: impuesto que le descuentas al proveedor y le entregas al SAT.
# Mientras no lo enteras, es dinero de terceros que traes en la bolsa.
CODE_ISR_WITHHELD = "2400"
CODE_VAT_WITHHELD = "2410"
CODE_INTEREST_EXPENSE = "5900"

# (code, name, type, parent_code)
DEFAULT_CHART = (
    ("1000", "Activo", "ASSET", None),
    ("1100", "Caja y Bancos", "ASSET", "1000"),
    ("1200", "Cuentas por Cobrar", "ASSET", "1000"),
    ("1190", "IVA acreditable pagado", "ASSET", "1000"),
    ("1191", "IVA acreditable pendiente de pago", "ASSET", "1000"),
    ("1300", "Otros Activos", "ASSET", "1000"),
    ("1400", "Activo Fijo", "ASSET", "1000"),
    ("1490", "Depreciación Acumulada", "ASSET", "1000"),
    ("2000", "Pasivo", "LIABILITY", None),
    ("2100", "Cuentas por Pagar", "LIABILITY", "2000"),
    ("2200", "Tarjetas de crédito", "LIABILITY", "2000"),
    ("2300", "Préstamos por Pagar", "LIABILITY", "2000"),
    ("2400", "ISR Retenido por Enterar", "LIABILITY", "2000"),
    ("2410", "IVA Retenido por Enterar", "LIABILITY", "2000"),
    ("2190", "IVA trasladado cobrado", "LIABILITY", "2000"),
    ("2191", "IVA trasladado pendiente de cobro", "LIABILITY", "2000"),
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
    ("5800", "Depreciación", "EXPENSE", "5000"),
    ("5900", "Intereses", "EXPENSE", "5000"),
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


def ledger_code_for(account_type: str) -> str:
    """Cuenta contable donde vive cada instrumento.

    Efectivo y bancos comparten 1100; las tarjetas viven en 2200 porque son
    deuda, no dinero disponible.
    """
    from app.models.financial_account import is_liability

    return CODE_CREDIT_CARDS if is_liability(account_type) else CODE_CASH_BANK
