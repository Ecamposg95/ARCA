"""Proyectos: qué trabajo deja dinero y cuál se lo come.

La rentabilidad se arma sumando los ingresos y gastos marcados con el proyecto.
Deliberadamente se lee de las operaciones y no del ledger: un proyecto es una
etiqueta de negocio, no una cuenta contable, y la contabilidad no cambia porque
un trabajo se llame de una forma u otra.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.income import Income
from app.models.project import Project
from app.models.receivable import Receivable


def _sum(db: Session, model, organization_id: str, project_id: str | None, column) -> Decimal:
    query = db.query(func.coalesce(func.sum(column), 0)).filter(
        model.organization_id == organization_id,
        model.status != "CANCELLED",
    )
    query = (
        query.filter(model.project_id == project_id)
        if project_id
        else query.filter(model.project_id.is_(None))
    )
    return Decimal(query.scalar() or 0)


def profitability(db: Session, organization_id: str, project_id: str | None = None) -> dict:
    """Ingresos, gastos y margen de un proyecto. Sin proyecto: lo no asignado."""
    # Se usa el subtotal, no el total: el IVA no es ingreso ni costo de nadie.
    revenue = _sum(db, Income, organization_id, project_id, Income.subtotal)
    cost = _sum(db, Expense, organization_id, project_id, Expense.subtotal)
    pending = _sum(db, Receivable, organization_id, project_id, Receivable.subtotal)

    margin = revenue - cost
    margin_pct = (margin / revenue * 100) if revenue > 0 else Decimal("0")

    return {
        "revenue": revenue,
        "cost": cost,
        "margin": margin,
        "margin_pct": round(margin_pct, 1),
        "pending_revenue": pending,
    }


def list_with_profitability(db: Session, organization_id: str, status: str | None = None) -> list[dict]:
    query = db.query(Project).filter(Project.organization_id == organization_id)
    if status:
        query = query.filter(Project.status == status)

    rows = []
    for project in query.order_by(Project.created_at.desc()).all():
        numbers = profitability(db, organization_id, project.id)
        rows.append(
            {
                **{c.name: getattr(project, c.name) for c in project.__table__.columns},
                **numbers,
                # Contra lo acordado: avisa antes de que el proyecto se coma el margen.
                "budget_used_pct": (
                    round(numbers["revenue"] / Decimal(project.budget) * 100, 1)
                    if project.budget
                    else None
                ),
            }
        )
    return rows


def create_project(
    db: Session,
    organization_id: str,
    *,
    name: str,
    code: str | None = None,
    customer_id: str | None = None,
    description: str | None = None,
    budget: Decimal | None = None,
    start_date=None,
    end_date=None,
    user_id: str | None = None,
) -> Project:
    project = Project(
        organization_id=organization_id,
        name=name,
        code=code,
        customer_id=customer_id,
        description=description,
        budget=budget,
        start_date=start_date,
        end_date=end_date,
        created_by=user_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def close_project(db: Session, project: Project) -> Project:
    project.status = "CLOSED"
    project.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project
