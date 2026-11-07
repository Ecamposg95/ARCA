"""Inicio «Tablero del día»: dinero hoy, pagos de la semana, autorizaciones y sucursales."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register

TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())
SUNDAY = MONDAY + timedelta(days=6)


def _company(client, email="lafe@example.com", initial_cash="1000", threshold=None):
    body = register(client, email=email, business="La Fe", initial_cash=initial_cash)
    headers = auth_headers(body)
    if threshold is not None:
        response = client.patch(
            "/api/organizations/current/approvals", headers=headers, json={"approval_threshold": threshold, "member_capture_limit": None}
        )
        assert response.status_code == 200, response.text
    return body["organization"]["id"], headers


def _member(client, owner_headers, email, role, can_authorize=False):
    invited = client.post(
        "/api/organizations/current/members",
        headers=owner_headers,
        json={"email": email, "name": role.title(), "role": role, "password": "supersegura123"},
    )
    assert invited.status_code == 201, invited.text
    if can_authorize:
        client.patch(f"/api/organizations/current/members/{invited.json()['id']}", headers=owner_headers, json={"can_authorize": True})
    login = client.post("/api/auth/login", json={"email": email, "password": "supersegura123"})
    return auth_headers(login.json())


def _account(client, headers, name, kind, opening="0", **extra):
    response = client.post("/api/accounts", headers=headers, json={"name": name, "type": kind, "opening_balance": opening, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _category(client, headers, name, kind):
    return next(c for c in client.get(f"/api/categories?kind={kind}", headers=headers).json() if c["name"] == name)


def _income(client, headers, when, amount, account_id=None):
    account_id = account_id or client.get("/api/accounts", headers=headers).json()[0]["id"]
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Venta",
            "amount": str(amount),
            "category_id": _category(client, headers, "Ventas", "INCOME")["id"],
            "financial_account_id": account_id,
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _payable(client, headers, due, amount, vendor="Reactivos del Norte", description="Reactivos"):
    vendors = client.get("/api/vendors", headers=headers).json()
    items = vendors["items"] if isinstance(vendors, dict) else vendors
    existing = next((v for v in items if v["name"] == vendor), None)
    vendor_id = existing["id"] if existing else client.post("/api/vendors", headers=headers, json={"name": vendor}).json()["id"]
    response = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor_id,
            "description": description,
            "amount": str(amount),
            "due_date": due.isoformat(),
            "category_id": _category(client, headers, "Renta", "EXPENSE")["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _today(client, headers, **params):
    response = client.get("/api/dashboard/today", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _rows(money):
    return {row["key"]: row for row in money["rows"]}


# --- Dinero hoy -------------------------------------------------------------


def test_dinero_parte_central_sucursales_bancos_transito(client):
    _, headers = _company(client)  # «Caja» del onboarding: central con 1,000
    unit = client.post("/api/business-units", headers=headers, json={"name": "Villas"}).json()
    _account(client, headers, "Caja Villas", "CASH", "200", business_unit_id=unit["id"])
    _account(client, headers, "Santander", "BANK", "5000")
    _account(client, headers, "NetPay", "PROCESSOR", "300", settlement_days=2)
    _account(client, headers, "AMEX", "CREDIT_CARD", "0")

    money = _today(client, headers)["money"]
    assert money["total"] == "6500.00" and money["available"] == "6200.00" and money["in_transit"] == "300.00"
    rows = _rows(money)
    assert [row["key"] for row in money["rows"]] == ["central", "branches", "banks", "processor"]
    assert rows["central"]["amount"] == "1000.00" and rows["central"]["status"] == "CONFIRMED"
    assert rows["branches"]["amount"] == "200.00" and rows["branches"]["status"] == "TO_COLLECT"
    assert rows["banks"]["amount"] == "5000.00" and rows["banks"]["status"] == "CONFIRMED"
    assert rows["processor"]["amount"] == "300.00" and rows["processor"]["status"] == "TO_DEPOSIT"
    assert money["next_settlement"] == {"account": "NetPay", "amount": "300.00", "expected_on": (TODAY + timedelta(days=2)).isoformat()}
    assert money["needs_opening"] is False


def test_banco_provisional_marca_needs_opening(client):
    _, headers = _company(client)
    cutoff = TODAY.replace(day=1)
    assert client.patch("/api/opening", headers=headers, json={"opening_date": cutoff.isoformat()}).status_code == 200
    bank = _account(client, headers, "Santander", "BANK", "0")

    money = _today(client, headers)["money"]
    assert money["needs_opening"] is True
    assert _rows(money)["banks"]["status"] == "PROVISIONAL"

    adjusted = client.post(
        f"/api/accounts/{bank['id']}/opening-adjustment",
        headers=headers,
        json={"target_opening_balance": "2500", "status": "CONFIRMED", "reason": "Estado de cuenta oct-2026"},
    )
    assert adjusted.status_code == 200, adjusted.text
    money = _today(client, headers)["money"]
    assert money["needs_opening"] is False and _rows(money)["banks"]["status"] == "CONFIRMED"
    assert _rows(money)["banks"]["amount"] == "2500.00"


def test_delta_contra_dia_habil_anterior(client, db):
    organization_id, headers = _company(client)
    _income(client, headers, TODAY, "500")
    money = _today(client, headers)["money"]
    assert money["total"] == "1500.00" and money["previous_close"] == "1000.00" and money["delta"] == "500.00"

    # Un lunes compara contra el viernes: lo del sábado y el domingo entra en el delta.
    from app.domains.dashboard.today import today as today_panel
    from app.models.organization import OrganizationMember

    organization_id, headers = _company(client, email="lunes@example.com")
    monday = TODAY - timedelta(days=TODAY.weekday()) - timedelta(days=7)
    _income(client, headers, monday - timedelta(days=1), "40")  # domingo
    _income(client, headers, monday - timedelta(days=2), "30")  # sábado
    _income(client, headers, monday - timedelta(days=3), "20")  # viernes: ya estaba al cierre
    membership = db.query(OrganizationMember).filter_by(organization_id=organization_id).first()
    panel = today_panel(db, organization_id, membership, week_of=monday, business_unit_id=None, fiscal_entity_id=None, today=monday)
    assert panel["money"]["delta"] == Decimal("70.00")
    assert panel["money"]["previous_close"] == panel["money"]["total"] - Decimal("70.00")


# --- Por pagar esta semana ---------------------------------------------------


def test_semana_lunes_a_domingo_con_saldo_corrido(client):
    _, headers = _company(client, initial_cash="10000")
    thursday = _payable(client, headers, MONDAY + timedelta(days=3), "500", description="Luz")
    tuesday = _payable(client, headers, MONDAY + timedelta(days=1), "1000")
    _payable(client, headers, MONDAY + timedelta(days=8), "9999", description="Semana que viene")
    assert client.post(
        f"/api/payables/{tuesday['id']}/pay",
        headers=headers,
        json={"amount": "250", "financial_account_id": client.get("/api/accounts", headers=headers).json()[0]["id"]},
    ).status_code == 200

    week = _today(client, headers, week_of=(MONDAY + timedelta(days=4)).isoformat())["week"]
    assert week["start"] == MONDAY.isoformat() and week["end"] == SUNDAY.isoformat()
    assert [(item["payable_id"], item["amount"], item["running_balance"], item["approval"], item["overdue"]) for item in week["items"]] == [
        (tuesday["id"], "750.00", "9000.00", None, False),
        (thursday["id"], "500.00", "8500.00", None, False),
    ]
    assert week["items"][0]["vendor"] == "Reactivos del Norte" and week["items"][0]["description"] == "Reactivos"
    assert week["items"][0]["due_date"] == (MONDAY + timedelta(days=1)).isoformat()
    assert week["total"] == "1250.00"
    assert [d["date"] for d in week["days"]] == [(MONDAY + timedelta(days=i)).isoformat() for i in range(7)]
    assert [d["amount"] for d in week["days"]] == ["0.00", "750.00", "0.00", "500.00", "0.00", "0.00", "0.00"]


def test_vencida_aparece_el_lunes(client):
    _, headers = _company(client)
    overdue = _payable(client, headers, MONDAY - timedelta(days=10), "300", description="Vencida")
    week = _today(client, headers)["week"]
    assert [(item["payable_id"], item["due_date"], item["overdue"]) for item in week["items"]] == [
        (overdue["id"], (MONDAY - timedelta(days=10)).isoformat(), True)
    ]
    assert week["days"][0]["amount"] == "300.00"


def test_por_autorizar_y_requiere_autorizacion(client):
    _, owner = _company(client, initial_cash="900000", threshold="100000")
    admin = _member(client, owner, "abraham@lafe.mx", "ADMIN")
    account = client.get("/api/accounts", headers=owner).json()[0]
    pending = _payable(client, owner, MONDAY + timedelta(days=1), "150000", description="Reactivos")
    required = _payable(client, owner, MONDAY + timedelta(days=2), "120000", description="Equipo")
    normal = _payable(client, owner, MONDAY + timedelta(days=3), "1000", description="Agua")
    submitted = client.post(
        f"/api/payables/{pending['id']}/pay", headers=admin, json={"amount": "150000", "financial_account_id": account["id"]}
    )
    assert submitted.status_code == 202, submitted.text

    body = _today(client, owner)
    approvals = {item["payable_id"]: item["approval"] for item in body["week"]["items"]}
    assert approvals == {pending["id"]: "PENDING", required["id"]: "REQUIRED", normal["id"]: None}
    assert body["week"]["days"][1]["pending_approval_amount"] == "150000.00"
    assert body["week"]["days"][2]["pending_approval_amount"] == "0.00"
    assert body["approvals"]["can_authorize"] is True
    assert body["approvals"]["pending"] == [
        {
            "proposal_id": submitted.json()["proposal_id"],
            "summary": "Pago de $150,000.00 a Reactivos del Norte · Reactivos",
            "amount": "150000.00",
            "requested_by_name": "Admin",
        }
    ]
    as_admin = _today(client, admin)
    assert as_admin["approvals"]["can_authorize"] is False and len(as_admin["approvals"]["pending"]) == 1


def test_member_ve_inicio(client):
    _, owner = _company(client)
    for email, role in (("aux@example.com", "MEMBER"), ("mira@example.com", "VIEWER")):
        body = _today(client, _member(client, owner, email, role))
        assert body["money"]["total"] == "1000.00"


def test_empresa_vacia_responde_ceros_y_listas_vacias(client):
    _, headers = _company(client, email="nueva@example.com", initial_cash=None)
    body = _today(client, headers)
    money = body["money"]
    assert money["total"] == "0.00" and money["delta"] == "0.00" and money["next_settlement"] is None
    assert all(row["amount"] == "0.00" for row in money["rows"])
    assert body["week"]["items"] == [] and body["week"]["total"] == "0.00" and len(body["week"]["days"]) == 7
    assert body["approvals"] == {"pending": [], "can_authorize": True}


# --- Sucursales ---------------------------------------------------------------

import calendar  # noqa: E402

from app.domains.analytics.points import ResolvedPoint, replace_points  # noqa: E402

MONTH = TODAY.replace(day=1)
YESTERDAY = TODAY - timedelta(days=1)


def _months_back(day: date, months: int) -> date:
    year, month = day.year, day.month - months
    while month <= 0:
        year, month = year - 1, month + 12
    return date(year, month, 1)


def _unit(client, headers, name, cash=True, active=True):
    unit = client.post("/api/business-units", headers=headers, json={"name": name}).json()
    account = _account(client, headers, f"Caja {name}", "CASH", "0", business_unit_id=unit["id"]) if cash else None
    if not active:
        client.patch(f"/api/business-units/{unit['id']}", headers=headers, json={"active": False})
    return unit, account


def _hist_unit(db, organization_id, unit_id, points):
    resolved = [
        ResolvedPoint("sales_daily", "net_sales", when, "day", Decimal(value), unit_label="X", business_unit_id=unit_id)
        for when, value in points
    ]
    replace_points(db, organization_id, source_family="toronja", source="toronja:f#ventas", points=resolved, user_id=None)


def _branches(client, headers, **params):
    return _today(client, headers, **params)["branches"]


def test_sucursales_ordenadas_por_venta(client):
    _, headers = _company(client)
    villas, caja_villas = _unit(client, headers, "Villas")
    morelos, caja_morelos = _unit(client, headers, "Morelos")
    _unit(client, headers, "Cumbres", active=False)
    _income(client, headers, TODAY, "300", caja_villas["id"])
    _income(client, headers, TODAY, "500", caja_morelos["id"])
    _income(client, headers, YESTERDAY - timedelta(days=3), "50", caja_villas["id"])
    _income(client, headers, YESTERDAY - timedelta(days=1), "20", caja_villas["id"])

    branches = _branches(client, headers)
    assert branches["month"] == MONTH.isoformat() and branches["origin"] == "live"
    villas_sales = Decimal("300") + sum(
        (Decimal(v) for d, v in ((YESTERDAY - timedelta(days=3), "50"), (YESTERDAY - timedelta(days=1), "20")) if d >= MONTH), Decimal("0")
    )
    share = (villas_sales / Decimal("500")).quantize(Decimal("0.01"))
    assert [(r["name"], r["sales"], r["share"]) for r in branches["rows"]] == [("Morelos", "500.00", "1.00"), ("Villas", f"{villas_sales:.2f}", str(share))]
    assert all(r["delta_pct"] is None and r["delta_basis"] is None for r in branches["rows"])
    spark = branches["rows"][1]["sparkline"]
    assert [(p["date"], p["value"]) for p in spark] == [
        ((YESTERDAY - timedelta(days=3)).isoformat(), "50.00"),
        ((YESTERDAY - timedelta(days=2)).isoformat(), "0.00"),
        ((YESTERDAY - timedelta(days=1)).isoformat(), "20.00"),
        (YESTERDAY.isoformat(), "0.00"),
    ]
    assert branches["rows"][0]["sparkline"] == []
    only_villas = _branches(client, headers, business_unit_id=villas["id"])
    assert [r["name"] for r in only_villas["rows"]] == ["Villas"]


def test_delta_vs_mismo_mes_anio_pasado(client, db):
    organization_id, headers = _company(client)
    assert client.patch("/api/opening", headers=headers, json={"opening_date": MONTH.isoformat()}).status_code == 200
    villas, caja = _unit(client, headers, "Villas")
    last_year = MONTH.replace(year=MONTH.year - 1)
    points = [(last_year, "100")]
    days_in_month = calendar.monthrange(last_year.year, last_year.month)[1]
    if TODAY.day < days_in_month:
        points.append((last_year.replace(day=TODAY.day + 1), "1000"))  # fuera del tramo de días: no cuenta
    _hist_unit(db, organization_id, villas["id"], points)
    _income(client, headers, TODAY, "300", caja["id"])

    row = _branches(client, headers)["rows"][0]
    assert row["delta_pct"] == "200.00" and row["delta_basis"] == "previous_year"


def test_delta_vs_promedio_3_meses_sin_anio_previo(client, db):
    organization_id, headers = _company(client)
    assert client.patch("/api/opening", headers=headers, json={"opening_date": MONTH.isoformat()}).status_code == 200
    morelos, caja = _unit(client, headers, "Morelos")
    _unit(client, headers, "Alameda")
    _hist_unit(
        db,
        organization_id,
        morelos["id"],
        [(_months_back(MONTH, 1), "400"), (_months_back(MONTH, 2), "200"), (_months_back(MONTH, 4), "600"), (_months_back(MONTH, 5), "9999")],
    )
    _income(client, headers, TODAY, "500", caja["id"])

    rows = {r["name"]: r for r in _branches(client, headers)["rows"]}
    assert rows["Morelos"]["delta_pct"] == "25.00" and rows["Morelos"]["delta_basis"] == "avg_3m"
    assert rows["Alameda"]["sales"] == "0.00" and rows["Alameda"]["delta_pct"] is None and rows["Alameda"]["delta_basis"] is None


def test_sin_venta_viva_usa_ultimo_mes_historico(client, db):
    organization_id, headers = _company(client)
    assert client.patch("/api/opening", headers=headers, json={"opening_date": MONTH.isoformat()}).status_code == 200
    villas, _ = _unit(client, headers, "Villas")
    morelos, _ = _unit(client, headers, "Morelos")
    _hist_unit(db, organization_id, villas["id"], [(_months_back(MONTH, 2) + timedelta(days=4), "700"), (_months_back(MONTH, 1) + timedelta(days=2), "100")])
    _hist_unit(db, organization_id, morelos["id"], [(_months_back(MONTH, 2) + timedelta(days=5), "900")])

    branches = _branches(client, headers)
    assert branches["origin"] == "historical" and branches["month"] == _months_back(MONTH, 1).isoformat()
    assert [(r["name"], r["sales"]) for r in branches["rows"]] == [("Villas", "100.00"), ("Morelos", "0.00")]


def test_estado_del_corte(client, db):
    from datetime import datetime, timezone

    from app.models.cash_cut import CashCut

    _, headers = _company(client)
    central = client.get("/api/accounts", headers=headers).json()[0]
    villas, caja_villas = _unit(client, headers, "Villas")
    morelos, caja_morelos = _unit(client, headers, "Morelos")
    _, caja_alameda = _unit(client, headers, "Alameda")
    _unit(client, headers, "Santa Anita")  # con caja pero sin movimientos ayer
    _unit(client, headers, "Empresas", cash=False)

    for caja in (caja_villas, caja_morelos, caja_alameda):
        _income(client, headers, YESTERDAY, "100", caja["id"])
    for caja in (caja_villas, caja_morelos):
        cut = client.post("/api/cash-cuts", headers=headers, json={"financial_account_id": caja["id"], "date": YESTERDAY.isoformat()})
        assert cut.status_code == 201, cut.text
        assert client.post(f"/api/cash-cuts/{cut.json()['id']}/count", headers=headers, json={"counted_amount": "100"}).status_code == 200
        delivered = client.post(
            f"/api/cash-cuts/{cut.json()['id']}/deliver",
            headers=headers,
            json={"delivered_amount": "100", "delivered_to_account_id": central["id"]},
        )
        assert delivered.status_code == 200, delivered.text
    villas_cut = db.query(CashCut).filter_by(financial_account_id=caja_villas["id"]).one()
    villas_cut.delivered_at = datetime(YESTERDAY.year, YESTERDAY.month, YESTERDAY.day, 23, 0, tzinfo=timezone.utc)  # 17:00 en México: mismo día
    db.commit()

    cuts = {r["name"]: r["cut"] for r in _branches(client, headers)["rows"]}
    assert cuts == {"Villas": "DELIVERED", "Morelos": "LATE", "Alameda": "MISSING", "Santa Anita": "NA", "Empresas": "NA"}


# --- Hallazgos de la revisión -------------------------------------------------


def test_ajuste_de_apertura_no_cuenta_en_el_delta(client, db):
    from app.domains.dashboard.today import today as today_panel
    from app.models.organization import OrganizationMember

    organization_id, headers = _company(client, email="apertura@example.com", initial_cash=None)
    cutoff = MONDAY - timedelta(days=14)
    assert client.patch("/api/opening", headers=headers, json={"opening_date": cutoff.isoformat()}).status_code == 200
    bank = _account(client, headers, "Santander", "BANK", "0")
    adjusted = client.post(
        f"/api/accounts/{bank['id']}/opening-adjustment",
        headers=headers,
        json={"target_opening_balance": "2500", "status": "CONFIRMED", "reason": "Estado de cuenta oct-2026"},
    )
    assert adjusted.status_code == 200, adjusted.text
    membership = db.query(OrganizationMember).filter_by(organization_id=organization_id).first()
    panel = today_panel(db, organization_id, membership, week_of=cutoff, business_unit_id=None, fiscal_entity_id=None, today=cutoff)
    assert panel["money"]["total"] == Decimal("2500.00")
    assert panel["money"]["delta"] == Decimal("0.00") and panel["money"]["previous_close"] == Decimal("2500.00")


def test_mes_de_respaldo_vivo_no_se_etiqueta_historico(client, db):
    from app.domains.dashboard.today import today as today_panel
    from app.models.organization import OrganizationMember

    organization_id, headers = _company(client, email="respaldo@example.com")
    last_month = _months_back(MONTH, 1)
    assert client.patch("/api/opening", headers=headers, json={"opening_date": last_month.isoformat()}).status_code == 200
    _, caja = _unit(client, headers, "Villas")
    _income(client, headers, last_month + timedelta(days=2), "300", caja["id"])
    membership = db.query(OrganizationMember).filter_by(organization_id=organization_id).first()
    panel = today_panel(db, organization_id, membership, week_of=MONTH, business_unit_id=None, fiscal_entity_id=None, today=MONTH)
    branches = panel["branches"]
    assert branches["month"] == last_month and branches["origin"] == "live"
    assert branches["rows"][0]["sales"] == Decimal("300.00")


def test_hoy_es_el_de_la_zona_horaria_de_la_empresa():
    from datetime import datetime, timezone

    from app.domains.dashboard.today import local_today
    from app.models.organization import Organization

    late_utc = datetime(2026, 11, 6, 23, 30, tzinfo=timezone.utc)  # 17:30 en la Ciudad de México
    assert local_today(Organization(timezone="America/Mexico_City"), now=late_utc) == date(2026, 11, 6)
    assert local_today(Organization(timezone="UTC"), now=late_utc) == date(2026, 11, 6)
    assert local_today(Organization(timezone="Asia/Tokyo"), now=late_utc) == date(2026, 11, 7)
    assert local_today(Organization(timezone="Zona/Inexistente"), now=late_utc) == date(2026, 11, 6)  # cae a México
