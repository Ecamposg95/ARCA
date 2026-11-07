"""Histórico de análisis: tablas, reemplazo por rango y aislamiento del libro."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.domains.analytics.points import Point, ResolvedPoint, replace_points
from app.models.financial_account import FinancialAccount
from app.models.historical import HistoricalLoad, HistoricalPoint
from tests.helpers import auth_headers, register


@pytest.fixture()
def org(client):
    body = register(client, email="historico@example.com", initial_cash="1000")
    return body["organization"]["id"], auth_headers(body)


def _pt(day: date, value: str, metric: str = "net_sales") -> ResolvedPoint:
    return ResolvedPoint(
        dataset="sales_daily",
        metric=metric,
        period_start=day,
        period_grain="day",
        value=Decimal(value),
        unit_label="VILLAS",
    )


def _counts(db, organization_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for point in db.query(HistoricalPoint).filter(HistoricalPoint.organization_id == organization_id).all():
        family = point.source.split(":", 1)[0]
        counts[family] = counts.get(family, 0) + 1
    return counts


def test_replace_points_reemplaza_solo_el_rango_y_la_familia(db, org):
    organization_id, _ = org
    replace_points(
        db,
        organization_id,
        source_family="toronja",
        source="toronja:v.xls#1",
        points=[
            _pt(date(2026, 1, 5), "100"),
            _pt(date(2026, 1, 20), "200"),
            _pt(date(2026, 2, 3), "300"),
            _pt(date(2026, 2, 10), "400"),
        ],
        user_id=None,
    )
    replace_points(
        db,
        organization_id,
        source_family="control_general",
        source="control_general:cg.xlsx#PROY",
        points=[_pt(date(2026, 1, 1), "999")],
        user_id=None,
    )
    replace_points(
        db,
        organization_id,
        source_family="toronja",
        source="toronja:v2.xls#1",
        points=[_pt(date(2026, 2, 3), "350"), _pt(date(2026, 3, 1), "500")],
        user_id=None,
    )

    assert _counts(db, organization_id) == {"toronja": 4, "control_general": 1}
    toronja = (
        db.query(HistoricalPoint)
        .filter(HistoricalPoint.organization_id == organization_id, HistoricalPoint.source.like("toronja:%"))
        .order_by(HistoricalPoint.period_start)
        .all()
    )
    assert [(p.period_start, p.value) for p in toronja] == [
        (date(2026, 1, 5), Decimal("100.00")),
        (date(2026, 1, 20), Decimal("200.00")),
        (date(2026, 2, 3), Decimal("350.00")),
        (date(2026, 3, 1), Decimal("500.00")),
    ]


def test_recargar_igual_deja_el_mismo_conteo(db, org):
    organization_id, _ = org
    points = [_pt(date(2026, 1, 5), "100"), _pt(date(2026, 1, 5), "2", metric="tickets")]
    first = replace_points(db, organization_id, source_family="toronja", source="toronja:v.xls#1", points=points, user_id=None)
    second = replace_points(db, organization_id, source_family="toronja", source="toronja:v.xls#1", points=points, user_id=None)

    assert _counts(db, organization_id) == {"toronja": 2}
    loads = db.query(HistoricalLoad).filter(HistoricalLoad.organization_id == organization_id).all()
    assert {load.id for load in loads} == {first.id, second.id}
    assert first.rows == 2 and first.period_from == date(2026, 1, 5) and first.period_to == date(2026, 1, 5)


def test_historico_no_toca_la_contabilidad(db, org, client):
    organization_id, headers = org
    before = client.get("/api/accounting/trial-balance", headers=headers).json()
    balances_before = sum(
        (acc.current_balance for acc in db.query(FinancialAccount).filter_by(organization_id=organization_id)),
        Decimal("0"),
    )

    replace_points(
        db,
        organization_id,
        source_family="toronja",
        source="toronja:v.xls#1",
        points=[_pt(date(2026, 1, 5), "100000")],
        user_id=None,
    )

    after = client.get("/api/accounting/trial-balance", headers=headers).json()
    balances_after = sum(
        (acc.current_balance for acc in db.query(FinancialAccount).filter_by(organization_id=organization_id)),
        Decimal("0"),
    )
    assert after == before
    assert balances_after == balances_before == Decimal("1000.00")


def test_otra_empresa_no_ve_los_puntos(db, org, client):
    organization_id, _ = org
    other = register(client, email="otra@example.com")["organization"]["id"]
    replace_points(db, organization_id, source_family="toronja", source="toronja:v.xls#1", points=[_pt(date(2026, 1, 5), "1")], user_id=None)
    assert db.query(HistoricalPoint).filter_by(organization_id=other).count() == 0


def test_point_es_inmutable_y_sin_ids():
    point = Point(dataset="sales_daily", metric="net_sales", period_start=date(2026, 1, 1), period_grain="day", value=Decimal("1"))
    with pytest.raises(FrozenInstanceError):
        point.value = Decimal("2")  # type: ignore[misc]
