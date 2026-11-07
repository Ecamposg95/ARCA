"""Serie de ventas que une el histórico (antes de la fecha de corte) con lo
registrado en ONE Finance (desde el corte). Nunca suma ambos para el mismo
día; un periodo sin dato no aparece.

Reglas (spec «Cómo se lee» y Definiciones 1 y 7):
- periodo < opening_date → histórico; ≥ → vivo; sin opening_date → todo vivo.
- El mes que contiene un corte a mitad de mes se arma con los días de Toronja
  anteriores al corte más lo vivo desde el corte, y sale como «live».
- Histórico mensual: la suma de `sales_daily` del mes si existe; si no,
  `sales_monthly` (PROY). Con filtro de unidad sólo `sales_daily`.
- Con filtro de contribuyente no hay histórico (el Excel no lo trae).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.imports.service import _resolved_toronja_settings
from app.models.historical import HistoricalPoint
from app.models.income import Income
from app.models.organization import Organization
from app.models.receivable import Receivable

ENTITY_NOTE = "El histórico no trae desglose por contribuyente"
SERIES = {("sales", "net_sales")}
ZERO = Decimal("0.00")


def _month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _period(day: date, grain: str) -> date:
    return day.replace(day=1) if grain == "month" else day


def _shift_year(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 de febrero
        return day.replace(year=day.year + years, day=28)


def live_sales(
    db: Session,
    organization_id: str,
    start: date,
    end: date,
    grain: str,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
) -> dict[date, Decimal]:
    """Venta registrada en ONE Finance por periodo: ingresos de la categoría de
    ventas más las cuentas por cobrar de esa categoría, sin cancelados."""
    category_id = _resolved_toronja_settings(db, organization_id)["income_category_id"]
    if category_id is None:
        return {}
    totals: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for model in (Income, Receivable):
        query = (
            db.query(model.date, func.sum(model.amount))
            .filter(
                model.organization_id == organization_id,
                model.category_id == category_id,
                model.status != "CANCELLED",
                model.date >= start,
                model.date <= end,
            )
            .group_by(model.date)
        )
        if business_unit_id:
            query = query.filter(model.business_unit_id == business_unit_id)
        if fiscal_entity_id:
            query = query.filter(model.fiscal_entity_id == fiscal_entity_id)
        for day, amount in query.all():
            totals[_period(day, grain)] += Decimal(amount or 0)
    return dict(totals)


def _historical(
    db: Session,
    organization_id: str,
    start: date,
    end: date,
    grain: str,
    business_unit_id: str | None,
) -> dict[date, Decimal]:
    """Histórico por periodo dentro de [start, end] (ya recortado al corte)."""
    if end < start:
        return {}
    base = db.query(HistoricalPoint.period_start, func.sum(HistoricalPoint.value)).filter(
        HistoricalPoint.organization_id == organization_id,
        HistoricalPoint.metric == "net_sales",
        HistoricalPoint.period_start >= start,
        HistoricalPoint.period_start <= end,
    )
    daily = base.filter(HistoricalPoint.dataset == "sales_daily")
    if business_unit_id:
        daily = daily.filter(HistoricalPoint.business_unit_id == business_unit_id)
    totals: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for day, amount in daily.group_by(HistoricalPoint.period_start).all():
        totals[_period(day, grain)] += Decimal(amount or 0)
    if grain == "month" and not business_unit_id:
        # Un mes partido por el corte (end no es fin de mes) sólo puede armarse
        # con días de Toronja: el mensual de PROY cubriría también los días vivos.
        monthly_end = end if end == _month_end(end) else end.replace(day=1) - timedelta(days=1)
        monthly = base.filter(
            HistoricalPoint.dataset == "sales_monthly",
            HistoricalPoint.period_start >= start.replace(day=1),
            HistoricalPoint.period_start <= monthly_end,
        )
        for month, amount in monthly.group_by(HistoricalPoint.period_start).all():
            if month not in totals:
                totals[month] = Decimal(amount or 0)
    return dict(totals)


def _points(
    db: Session,
    organization_id: str,
    opening: date | None,
    start: date,
    end: date,
    grain: str,
    business_unit_id: str | None,
    fiscal_entity_id: str | None,
) -> list[dict]:
    live = live_sales(db, organization_id, max(start, opening) if opening else start, end, grain, business_unit_id, fiscal_entity_id)
    hist: dict[date, Decimal] = {}
    if opening and not fiscal_entity_id:
        hist = _historical(db, organization_id, start, min(end, opening - timedelta(days=1)), grain, business_unit_id)
    today_period = _period(date.today(), grain)
    boundary = _period(opening, grain) if opening else None
    points = []
    for period in sorted(set(hist) | set(live)):
        if boundary is None or period >= boundary:
            if period not in live and period != boundary:
                continue
            value = live.get(period, ZERO) + (hist.get(period, ZERO) if period == boundary else ZERO)
            origin = "live"
        else:
            value = hist[period]
            origin = "historical"
        points.append({"period": period, "value": value.quantize(ZERO), "origin": origin, "partial": period == today_period})
    return points


def series(
    db: Session,
    organization_id: str,
    *,
    metric: str,
    start: date,
    end: date,
    grain: str,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
    compare: str | None = None,
    dataset: str = "sales",
) -> dict:
    if (dataset, metric) not in SERIES or grain not in ("day", "month"):
        raise ValueError("Serie no disponible")
    if end < start:
        raise ValueError("El rango de fechas está invertido")
    organization = db.get(Organization, organization_id)
    opening = organization.opening_date if organization else None

    points = _points(db, organization_id, opening, start, end, grain, business_unit_id, fiscal_entity_id)
    previous = None
    if compare == "previous_year":
        previous = [
            {"period": p["period"], "value": p["value"], "origin": p["origin"]}
            for p in _points(db, organization_id, opening, _shift_year(start, -1), _shift_year(end, -1), grain, business_unit_id, fiscal_entity_id)
        ]
    target = None
    if grain == "month" and not business_unit_id and not fiscal_entity_id:
        rows = (
            db.query(HistoricalPoint.period_start, func.sum(HistoricalPoint.value))
            .filter(
                HistoricalPoint.organization_id == organization_id,
                HistoricalPoint.dataset == "sales_target",
                HistoricalPoint.metric == "target",
                HistoricalPoint.period_start >= start.replace(day=1),
                HistoricalPoint.period_start <= end,
            )
            .group_by(HistoricalPoint.period_start)
            .order_by(HistoricalPoint.period_start)
            .all()
        )
        target = [{"period": month, "value": Decimal(amount or 0).quantize(ZERO)} for month, amount in rows] or None

    historical_available = any(p["origin"] == "historical" for p in points) or (
        opening is not None and not fiscal_entity_id and _has_history(db, organization_id)
    )
    return {
        "points": points,
        "previous": previous,
        "target": target,
        "opening_date": opening,
        "historical_available": historical_available,
        "historical_note": ENTITY_NOTE if fiscal_entity_id else None,
    }


def _has_history(db: Session, organization_id: str) -> bool:
    return (
        db.query(HistoricalPoint.id)
        .filter(HistoricalPoint.organization_id == organization_id, HistoricalPoint.metric == "net_sales")
        .first()
        is not None
    )


def sales_by_unit_day(
    db: Session,
    organization_id: str,
    opening: date | None,
    start: date,
    end: date,
    fiscal_entity_id: str | None = None,
) -> dict[tuple[str, date], Decimal]:
    """Venta diaria por unidad: histórico (`sales_daily` con unidad) antes del
    corte y lo registrado desde el corte. Sin corte, sólo lo registrado."""
    totals: dict[tuple[str, date], Decimal] = defaultdict(lambda: ZERO)
    live_start = max(start, opening) if opening else start
    if live_start <= end:
        category_id = _resolved_toronja_settings(db, organization_id)["income_category_id"]
        if category_id is not None:
            for model in (Income, Receivable):
                query = (
                    db.query(model.business_unit_id, model.date, func.sum(model.amount))
                    .filter(
                        model.organization_id == organization_id,
                        model.category_id == category_id,
                        model.status != "CANCELLED",
                        model.business_unit_id.isnot(None),
                        model.date >= live_start,
                        model.date <= end,
                    )
                    .group_by(model.business_unit_id, model.date)
                )
                if fiscal_entity_id:
                    query = query.filter(model.fiscal_entity_id == fiscal_entity_id)
                for unit_id, day, amount in query.all():
                    totals[(unit_id, day)] += Decimal(amount or 0)
    if opening and not fiscal_entity_id and start < opening:
        rows = (
            db.query(HistoricalPoint.business_unit_id, HistoricalPoint.period_start, func.sum(HistoricalPoint.value))
            .filter(
                HistoricalPoint.organization_id == organization_id,
                HistoricalPoint.dataset == "sales_daily",
                HistoricalPoint.metric == "net_sales",
                HistoricalPoint.business_unit_id.isnot(None),
                HistoricalPoint.period_start >= start,
                HistoricalPoint.period_start < opening,
                HistoricalPoint.period_start <= end,
            )
            .group_by(HistoricalPoint.business_unit_id, HistoricalPoint.period_start)
            .all()
        )
        for unit_id, day, amount in rows:
            totals[(unit_id, day)] += Decimal(amount or 0)
    return dict(totals)
