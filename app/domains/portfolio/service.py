"""Cartera: todas las empresas de un usuario y lo que cada una tiene pendiente.

La única puerta de entrada es el usuario de la sesión: las empresas salen de sus
membresías, nunca de un identificador que mande el cliente.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session

from app.domains.dashboard.service import available_cash, outstanding
from app.domains.periods.service import is_closed
from app.domains.portfolio.status import STATUS_ORDER, portfolio_status, previous_month
from app.models.accounting import JournalEntry
from app.models.agent import AgentProposal
from app.models.organization import Organization, OrganizationMember
from app.models.payable import Payable
from app.models.period import PeriodLock
from app.models.receivable import Receivable


def _has_entries(db: Session, organization_id: str, year: int, month: int) -> bool:
    """¿Hubo pólizas ese mes? Se decide por actividad en el libro, no por la
    fecha de alta: una empresa migrada con historia sí tiene mes que cerrar."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .first()
        is not None
    )


def _last_closed_period(db: Session, organization_id: str) -> str | None:
    lock = (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.reopened_at.is_(None),
        )
        .order_by(PeriodLock.year.desc(), PeriodLock.month.desc())
        .first()
    )
    return f"{lock.year}-{lock.month:02d}" if lock else None


def _pending_proposals(db: Session, organization_id: str) -> int:
    return (
        db.query(AgentProposal)
        .filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.status == "PROPOSED",
        )
        .count()
    )


def portfolio(db: Session, user_id: str) -> list[dict]:
    """Una fila por empresa del usuario, lo urgente arriba."""
    today = date.today()
    year, month = previous_month(today)

    rows = (
        db.query(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .filter(OrganizationMember.user_id == user_id)
        .all()
    )

    items: list[dict] = []
    for membership, organization in rows:
        org_id = organization.id
        closed = is_closed(db, org_id, year, month)
        payable_overdue = outstanding(db, org_id, Payable, overdue_only=True)
        pending = _pending_proposals(db, org_id)
        status, reasons = portfolio_status(
            today=today,
            previous_month_active=_has_entries(db, org_id, year, month),
            previous_month_closed=closed,
            payable_overdue=payable_overdue,
            pending_proposals=pending,
        )
        items.append(
            {
                "organization_id": org_id,
                "name": organization.name,
                "tax_id": organization.tax_id,
                "business_type": organization.business_type,
                "role": membership.role,
                "cash": available_cash(db, org_id),
                "receivable": outstanding(db, org_id, Receivable),
                "payable_overdue": payable_overdue,
                "last_closed_period": _last_closed_period(db, org_id),
                "previous_month_closed": closed,
                "pending_proposals": pending,
                "status": status,
                "reasons": reasons,
            }
        )

    items.sort(key=lambda item: (STATUS_ORDER[item["status"]], item["name"].lower()))
    return items
