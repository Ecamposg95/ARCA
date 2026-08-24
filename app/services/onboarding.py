"""Provisión de una organización nueva (cadena de onboarding, task pack §29).

Create User (fuera) → Create Organization → OWNER → Seed CoA →
Seed categorías → Cuenta "Caja" con saldo inicial.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationMember, ROLE_OWNER
from app.models.user import User


def provision_organization(
    db: Session,
    user: User,
    business_name: str,
    business_type: str | None = None,
    initial_cash: Decimal | None = None,
) -> Organization:
    """Crea la organización con todo lo necesario para operar. No hace commit."""
    organization = Organization(name=business_name.strip(), business_type=business_type)
    db.add(organization)
    db.flush()

    db.add(
        OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role=ROLE_OWNER,
        )
    )

    # Seeds contables y cuenta inicial (se conectan en cuanto existen los módulos):
    from app.services.accounting.coa import seed_chart_of_accounts
    from app.services.categories import seed_default_categories
    from app.domains.financial_accounts.service import create_financial_account

    seed_chart_of_accounts(db, organization.id)
    seed_default_categories(db, organization.id)
    create_financial_account(
        db,
        organization_id=organization.id,
        name="Caja",
        account_type="CASH",
        opening_balance=initial_cash or Decimal("0"),
        created_by=user.id,
    )
    return organization
