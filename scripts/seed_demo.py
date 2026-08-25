"""Datos demo para desarrollo (task pack §41). NUNCA en producción.

Uso:
    python scripts/seed_demo.py

Crea "Atlas Software Consulting" (demo@arca.test / demodemo123) — una
consultora de software con 5 clientes, 5 proveedores, 2 cuentas de banco
y ~4 meses de ingresos y gastos.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Los datos demo no se cargan en producción.")

    import app.models  # noqa: F401
    from app.database import Base, SessionLocal, engine
    from app.domains.expenses.schemas import ExpenseCreate
    from app.domains.expenses.service import create_expense
    from app.domains.financial_accounts.service import create_financial_account
    from app.domains.income.schemas import IncomeCreate
    from app.domains.income.service import create_income
    from app.models.category import Category
    from app.models.contact import Customer, Vendor
    from app.models.user import User
    from app.domains.auth.service import register_user

    Base.metadata.create_all(bind=engine)  # entorno local; producción usa Alembic
    db = SessionLocal()
    random.seed(42)

    if db.query(User).filter(User.email == "demo@arca.test").first():
        print("La empresa demo ya existe (demo@arca.test).")
        return

    user, organization = register_user(
        db,
        email="demo@arca.test",
        password="demodemo123",
        name="Demo Atlas",
        business_name="Atlas Software Consulting",
        business_type="services",
        initial_cash=Decimal("25000"),
    )

    bank_1 = create_financial_account(
        db, organization.id, "BBVA Operativa", "BANK", Decimal("80000"), institution="BBVA", created_by=user.id
    )
    bank_2 = create_financial_account(
        db, organization.id, "Santander Nómina", "BANK", Decimal("35000"), institution="Santander", created_by=user.id
    )
    db.commit()

    customers = []
    for name in (
        "Grupo Industrial del Norte",
        "Fintech Pagos MX",
        "Clínica Los Álamos",
        "Retail Vega",
        "Constructora Ríos",
    ):
        customer = Customer(organization_id=organization.id, name=name)
        db.add(customer)
        customers.append(customer)
    vendors = []
    for name in (
        "WeWork Reforma",
        "Amazon Web Services",
        "Google Workspace",
        "Despacho Contable Núñez",
        "Telmex Negocios",
    ):
        vendor = Vendor(organization_id=organization.id, name=name)
        db.add(vendor)
        vendors.append(vendor)
    db.commit()

    income_categories = (
        db.query(Category).filter(Category.organization_id == organization.id, Category.kind == "INCOME").all()
    )
    expense_categories = (
        db.query(Category).filter(Category.organization_id == organization.id, Category.kind == "EXPENSE").all()
    )
    accounts = [bank_1, bank_2]

    today = date.today()
    start = today - timedelta(days=120)
    cursor = start
    while cursor <= today:
        for _ in range(random.randint(1, 3)):
            create_income(
                db,
                organization.id,
                IncomeCreate(
                    date=cursor,
                    description=random.choice(
                        ("Desarrollo de software", "Proyecto web", "Iguala mensual de soporte", "Consultoría técnica", "Implementación ERP")
                    ),
                    amount=Decimal(random.randint(1500, 18000)),
                    category_id=random.choice(income_categories).id,
                    customer_id=random.choice(customers).id,
                    financial_account_id=random.choice(accounts).id,
                    status="PAID",
                ),
                created_by=user.id,
            )
        for _ in range(random.randint(1, 2)):
            create_expense(
                db,
                organization.id,
                ExpenseCreate(
                    date=cursor,
                    description=random.choice(
                        ("Renta coworking", "Factura AWS", "Licencias de software", "Publicidad LinkedIn", "Internet y telefonía", "Nómina quincenal")
                    ),
                    amount=Decimal(random.randint(300, 9000)),
                    category_id=random.choice(expense_categories).id,
                    vendor_id=random.choice(vendors).id,
                    financial_account_id=random.choice(accounts).id,
                    status="PAID",
                ),
                created_by=user.id,
            )
        cursor += timedelta(days=random.randint(2, 5))

    # CxC y CxP: una vencida, una con cobro parcial, compromisos abiertos
    from app.domains.payables.schemas import PayableCreate
    from app.domains.payables.service import create_payable
    from app.domains.receivables.schemas import ReceivableCreate
    from app.domains.receivables.service import collect_receivable, create_receivable

    ventas = next(c for c in income_categories if c.name == "Ventas")
    renta = next(c for c in expense_categories if c.name == "Renta")

    overdue = create_receivable(
        db,
        organization.id,
        ReceivableCreate(
            customer_id=customers[0].id,
            description="Factura 0012 — proyecto web",
            amount=Decimal("38000"),
            due_date=today - timedelta(days=20),
            category_id=ventas.id,
        ),
        created_by=user.id,
    )
    partial = create_receivable(
        db,
        organization.id,
        ReceivableCreate(
            customer_id=customers[1].id,
            description="Iguala agosto",
            amount=Decimal("24000"),
            due_date=today + timedelta(days=15),
            category_id=ventas.id,
        ),
        created_by=user.id,
    )
    collect_receivable(db, organization.id, partial, Decimal("10000"), bank_1.id, today, user.id)
    _ = overdue

    create_payable(
        db,
        organization.id,
        PayableCreate(
            vendor_id=vendors[0].id,
            description="Renta septiembre",
            amount=Decimal("18500"),
            due_date=today + timedelta(days=10),
            category_id=renta.id,
        ),
        created_by=user.id,
    )

    db.commit()
    print("Empresa demo lista: demo@arca.test / demodemo123")


if __name__ == "__main__":
    main()
