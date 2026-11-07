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
