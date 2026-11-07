"""Serie de ventas: histórico antes del corte, lo registrado en ONE Finance después."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.analytics.points import ResolvedPoint, replace_points
from app.domains.analytics.series import series
from tests.helpers import auth_headers, register

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)
# Un corte al día 1 del mes en curso y datos vivos de este mes: el test no depende del calendario.
CUTOFF = THIS_MONTH
LAST_MONTH = (THIS_MONTH - timedelta(days=1)).replace(day=1)
LAST_YEAR = TODAY.year - 1


def _company(client, email="lafe@example.com", cutoff=CUTOFF):
    body = register(client, email=email, business="La Fe", initial_cash="1000")
    headers = auth_headers(body)
    if cutoff is not None:
        response = client.patch("/api/opening", headers=headers, json={"opening_date": cutoff.isoformat()})
        assert response.status_code == 200, response.text
    return body["organization"]["id"], headers


def _category(client, headers, name, kind="INCOME"):
    return next(c for c in client.get(f"/api/categories?kind={kind}", headers=headers).json() if c["name"] == name)


def _income(client, headers, when, amount, category="Ventas", status="PAID", **dims):
    account = client.get("/api/accounts", headers=headers).json()[0]
    payload = {
        "date": when.isoformat(),
        "description": "Venta",
        "amount": str(amount),
        "category_id": _category(client, headers, category)["id"],
        "financial_account_id": account["id"],
        "status": status,
        **dims,
    }
    response = client.post("/api/income", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _receivable(client, headers, when, amount, **dims):
    customer = client.post("/api/customers", headers=headers, json={"name": "Empresa X"}).json()
    payload = {
        "customer_id": customer["id"],
        "description": "Adeudo",
        "amount": str(amount),
        "date": when.isoformat(),
        "due_date": (when + timedelta(days=30)).isoformat(),
        "category_id": _category(client, headers, "Ventas")["id"],
        **dims,
    }
    response = client.post("/api/receivables", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _hist(db, organization_id, points, family="toronja", unit_id=None):
    resolved = []
    for dataset, metric, when, value in points:
        grain = "day" if dataset == "sales_daily" else "month"
        resolved.append(
            ResolvedPoint(dataset, metric, when, grain, Decimal(value), unit_label="X" if unit_id else None, business_unit_id=unit_id)
        )
    replace_points(db, organization_id, source_family=family, source=f"{family}:f#s", points=resolved, user_id=None)


def _series(db, organization_id, **kwargs):
    defaults = dict(metric="net_sales", start=date(TODAY.year, 1, 1), end=date(TODAY.year, 12, 31), grain="month")
    defaults.update(kwargs)
    return series(db, organization_id, **defaults)


def pt(result, when: date):
    return next((p for p in result["points"] if p["period"] == when), None)


def test_antes_del_corte_historico_despues_vivo(client, db):
    organization_id, headers = _company(client)
    _hist(db, organization_id, [("sales_daily", "net_sales", LAST_MONTH + timedelta(days=2), "400"), ("sales_daily", "net_sales", LAST_MONTH + timedelta(days=9), "500")])
    _income(client, headers, CUTOFF + timedelta(days=1) if CUTOFF + timedelta(days=1) <= TODAY else CUTOFF, "100")

    result = _series(db, organization_id)
    last, current = pt(result, LAST_MONTH), pt(result, THIS_MONTH)
    assert last["origin"] == "historical" and last["value"] == Decimal("900.00") and last["partial"] is False
    assert current["origin"] == "live" and current["value"] == Decimal("100.00") and current["partial"] is True
    assert result["opening_date"] == CUTOFF and result["historical_available"] is True and result["historical_note"] is None


def test_corte_a_mitad_de_mes_no_duplica(client, db):
    cutoff = LAST_MONTH + timedelta(days=14)  # día 15 del mes pasado
    organization_id, headers = _company(client, cutoff=cutoff)
    _hist(
        db,
        organization_id,
        [
            ("sales_daily", "net_sales", LAST_MONTH + timedelta(days=9), "100"),
            ("sales_daily", "net_sales", LAST_MONTH + timedelta(days=13), "200"),
            ("sales_daily", "net_sales", LAST_MONTH + timedelta(days=19), "999"),  # Toronja después del corte: no cuenta
            ("sales_monthly", "net_sales", LAST_MONTH, "5000"),  # PROY del mes partido: tampoco
        ],
    )
    _income(client, headers, LAST_MONTH + timedelta(days=19), "50")

    result = _series(db, organization_id)
    month = pt(result, LAST_MONTH)
    assert month["value"] == Decimal("350.00") and month["origin"] == "live"

    days = _series(db, organization_id, start=LAST_MONTH, end=LAST_MONTH + timedelta(days=27), grain="day")
    assert pt(days, LAST_MONTH + timedelta(days=13))["origin"] == "historical"
    assert pt(days, LAST_MONTH + timedelta(days=19))["value"] == Decimal("50.00")
    assert pt(days, LAST_MONTH + timedelta(days=19))["origin"] == "live"
    assert pt(days, LAST_MONTH + timedelta(days=20)) is None  # sin dato: no aparece


def test_sin_corte_todo_vivo_y_sin_historico(client, db):
    organization_id, headers = _company(client, email="demo@example.com", cutoff=None)
    _hist(db, organization_id, [("sales_daily", "net_sales", LAST_MONTH + timedelta(days=2), "400")])
    _income(client, headers, TODAY, "100")

    result = _series(db, organization_id)
    assert result["historical_available"] is False and result["opening_date"] is None
    assert [(p["period"], p["value"], p["origin"]) for p in result["points"]] == [(THIS_MONTH, Decimal("100.00"), "live")]


def test_filtro_contribuyente_oculta_historico(client, db):
    organization_id, headers = _company(client)
    entity = client.post("/api/fiscal-entities", headers=headers, json={"name": "Liza"}).json()
    _hist(db, organization_id, [("sales_daily", "net_sales", LAST_MONTH + timedelta(days=2), "400")])
    _income(client, headers, TODAY, "100", fiscal_entity_id=entity["id"])
    _income(client, headers, TODAY, "70")

    result = _series(db, organization_id, fiscal_entity_id=entity["id"])
    assert result["historical_available"] is False
    assert result["historical_note"] == "El histórico no trae desglose por contribuyente"
    assert [(p["period"], p["value"]) for p in result["points"]] == [(THIS_MONTH, Decimal("100.00"))]


def test_2025_sale_de_proy_y_2026_de_toronja(client, db):
    organization_id, headers = _company(client)
    sep, aug = date(TODAY.year, 9, 1), date(TODAY.year, 8, 1)
    if sep >= CUTOFF:
        pytest.skip("el test supone corte después de septiembre")
    unit = client.post("/api/business-units", headers=headers, json={"name": "Villas"}).json()
    _hist(
        db,
        organization_id,
        [
            ("sales_monthly", "net_sales", date(LAST_YEAR, 9, 1), "573522"),
            ("sales_monthly", "net_sales", sep, "888242"),
            ("sales_monthly", "net_sales", aug, "800000"),
        ],
        family="control_general",
    )
    _hist(db, organization_id, [("sales_daily", "net_sales", sep + timedelta(days=1), "892011")], unit_id=unit["id"])

    result = _series(db, organization_id, start=date(LAST_YEAR, 1, 1))
    assert pt(result, date(LAST_YEAR, 9, 1))["value"] == Decimal("573522.00")
    assert pt(result, sep)["value"] == Decimal("892011.00")  # Toronja manda sobre PROY
    assert pt(result, aug)["value"] == Decimal("800000.00")  # sin Toronja, PROY

    by_unit = _series(db, organization_id, start=date(LAST_YEAR, 1, 1), business_unit_id=unit["id"])
    assert pt(by_unit, sep)["value"] == Decimal("892011.00")
    assert pt(by_unit, aug) is None and pt(by_unit, date(LAST_YEAR, 9, 1)) is None  # PROY no trae unidad


def test_ingreso_cancelado_y_otros_ingresos_no_cuentan(client, db):
    organization_id, headers = _company(client)
    _income(client, headers, TODAY, "100")
    cancelled = _income(client, headers, TODAY, "50")
    assert client.post(f"/api/income/{cancelled['id']}/cancel", headers=headers, json={"reason": "error"}).status_code == 200
    _income(client, headers, TODAY, "999", category="Otros ingresos")
    _receivable(client, headers, TODAY, "30")

    result = _series(db, organization_id)
    assert pt(result, THIS_MONTH)["value"] == Decimal("130.00")


def test_compare_con_anio_anterior_y_meta(client, db):
    organization_id, headers = _company(client)
    _hist(
        db,
        organization_id,
        [
            ("sales_monthly", "net_sales", date(LAST_YEAR, 3, 1), "10"),
            ("sales_target", "target", date(TODAY.year + 1, 1, 1), "77"),
        ],
        family="control_general",
    )
    result = _series(db, organization_id, compare="previous_year")
    assert result["previous"] == [{"period": date(LAST_YEAR, 3, 1), "value": Decimal("10.00"), "origin": "historical"}]
    assert result["target"] is None
    with_target = _series(db, organization_id, start=date(TODAY.year + 1, 1, 1), end=date(TODAY.year + 1, 12, 31))
    assert with_target["target"] == [{"period": date(TODAY.year + 1, 1, 1), "value": Decimal("77.00")}]
    assert _series(db, organization_id)["previous"] is None


def test_serie_desconocida_400(client, db):
    organization_id, _ = _company(client)
    with pytest.raises(ValueError, match="Serie no disponible"):
        _series(db, organization_id, metric="tickets")


def _member(client, owner_headers, email, role):
    response = client.post(
        "/api/organizations/current/members",
        headers=owner_headers,
        json={"email": email, "name": role, "role": role, "password": "supersegura123"},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={"email": email, "password": "supersegura123"})
    return auth_headers(login.json())


URL = f"/api/analytics/series?dataset=sales&metric=net_sales&from={TODAY.year}-01-01&to={TODAY.year}-12-31&grain=month&compare=previous_year"


def test_member_y_viewer_ven_la_serie(client, db):
    organization_id, owner = _company(client)
    _hist(db, organization_id, [("sales_daily", "net_sales", LAST_MONTH + timedelta(days=2), "400")])
    for email, role in (("aux@example.com", "MEMBER"), ("mira@example.com", "VIEWER")):
        response = client.get(URL, headers=_member(client, owner, email, role))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["points"][0] == {"period": LAST_MONTH.isoformat(), "value": "400.00", "origin": "historical", "partial": False}
        assert body["opening_date"] == CUTOFF.isoformat() and body["historical_available"] is True
    assert client.get(URL.replace("metric=net_sales", "metric=tickets"), headers=owner).status_code == 400
    assert client.get(URL.replace("dataset=sales", "dataset=pnl"), headers=owner).status_code == 400


def test_otra_empresa_no_ve_el_historico(client, db):
    organization_id, _ = _company(client)
    _hist(db, organization_id, [("sales_daily", "net_sales", LAST_MONTH + timedelta(days=2), "400")])
    other = _company(client, email="otra@example.com")[1]
    body = client.get(URL, headers=other).json()
    assert body["points"] == [] and body["historical_available"] is False
