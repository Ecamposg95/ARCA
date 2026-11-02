"""Presupuesto del asistente: USD por empresa y mes calendario (America/Mexico_City).

Antes de cada llamada al API se compara el consumo del mes más una estimación
mínima contra el tope; si no alcanza, no se llama. El consumo sale de
`ai_usage` (una fila por llamada), nunca de un contador aparte.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.assistant import AiUsage
from app.models.organization import Organization

MEXICO = ZoneInfo("America/Mexico_City")
# Una llamada corta a Opus con el system cacheado ronda medio centavo; se
# reserva un centavo para no cruzar el tope por una última llamada.
MIN_CALL_USD = Decimal("0.01")


class BudgetExhausted(Exception):
    """No hay presupuesto para una llamada más este mes."""

    def __init__(self, spent: Decimal, budget: Decimal):
        self.spent, self.budget = spent, budget
        super().__init__(budget_message(spent, budget))


def budget_message(spent: Decimal, budget: Decimal) -> str:
    return (
        f"Se agotó el presupuesto del asistente de este mes ({_money(spent)} de {_money(budget)} USD). "
        "Pídele a Atlas que lo amplíe."
    )


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """[inicio, fin) del mes calendario en México, expresado en UTC."""
    now = (now or datetime.now(timezone.utc)).astimezone(MEXICO)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def month_spend(db: Session, org_id: str, now: datetime | None = None) -> Decimal:
    start, end = month_bounds(now)
    total = (
        db.query(func.coalesce(func.sum(AiUsage.cost_usd), 0))
        .filter(AiUsage.organization_id == org_id, AiUsage.created_at >= start, AiUsage.created_at < end)
        .scalar()
    )
    return Decimal(str(total or 0)).quantize(Decimal("0.000001"))


def budget_for(organization: Organization) -> Decimal:
    if organization.ai_budget_usd is not None:
        return Decimal(organization.ai_budget_usd)
    return get_settings().ai_budget_default_usd


@dataclass(frozen=True)
class BudgetStatus:
    budget_usd: Decimal
    spent_usd: Decimal

    @property
    def remaining_usd(self) -> Decimal:
        return max(self.budget_usd - self.spent_usd, Decimal("0"))

    @property
    def exhausted(self) -> bool:
        return self.spent_usd + MIN_CALL_USD >= self.budget_usd


def budget_status(db: Session, organization: Organization, now: datetime | None = None) -> BudgetStatus:
    return BudgetStatus(budget_usd=budget_for(organization), spent_usd=month_spend(db, organization.id, now))


def ensure_budget(db: Session, organization: Organization) -> BudgetStatus:
    status = budget_status(db, organization)
    if status.exhausted:
        raise BudgetExhausted(status.spent_usd, status.budget_usd)
    return status
