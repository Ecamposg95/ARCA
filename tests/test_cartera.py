"""Cartera: el contador ve todas sus empresas, y sólo las suyas."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _bearer(auth_body: dict) -> dict:
    """Sólo la sesión, sin empresa activa: la cartera no depende de ella."""
    return {"Authorization": f"Bearer {auth_body['access_token']}"}


def _portfolio(client, auth_body: dict) -> dict:
    response = client.get("/api/portfolio", headers=_bearer(auth_body))
    assert response.status_code == 200, response.text
    return response.json()


def _previous_month() -> tuple[int, int]:
    end = date.today().replace(day=1) - timedelta(days=1)
    return end.year, end.month


def _category(client, headers, kind: str, name: str) -> dict:
    return next(
        c
        for c in client.get(f"/api/categories?kind={kind}", headers=headers).json()
        if c["name"] == name
    )


def _income_last_month(client, headers):
    year, month = _previous_month()
    account = client.get("/api/accounts", headers=headers).json()[0]
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date(year, month, 15).isoformat(),
            "description": "Venta",
            "amount": "5000",
            "category_id": _category(client, headers, "INCOME", "Ventas")["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _overdue_payable(client, headers, amount="4000") -> dict:
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Inmobiliaria Centro"}).json()
    response = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Renta",
            "amount": amount,
            "due_date": (date.today() - timedelta(days=5)).isoformat(),
            "category_id": _category(client, headers, "EXPENSE", "Renta")["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _invite(client, owner_headers, email: str):
    response = client.post(
        "/api/organizations/current/members",
        headers=owner_headers,
        json={"email": email, "name": "Contador", "role": "ACCOUNTANT", "password": "supersegura123"},
    )
    assert response.status_code == 201, response.text


def test_requires_a_session(client):
    assert client.get("/api/portfolio").status_code == 401


def test_lists_only_my_companies(client):
    ana = register(client, email="ana@example.com", business="Ferretería Ana")
    beto = register(client, email="beto@example.com", business="Taller Beto")

    mine = _portfolio(client, ana)
    assert mine["total"] == 1
    assert [item["name"] for item in mine["items"]] == ["Ferretería Ana"]
    assert mine["items"][0]["role"] == "OWNER"

    theirs = _portfolio(client, beto)
    assert [item["name"] for item in theirs["items"]] == ["Taller Beto"]


def test_an_invited_accountant_sees_the_company_with_that_role(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    owner = register(client, email="duena@example.com", business="Clínica")
    _invite(client, auth_headers(owner), "contador@example.com")

    # Con dos empresas y sin encabezado de empresa activa, la cartera responde igual.
    body = _portfolio(client, contador)
    assert body["total"] == 2
    roles = {item["name"]: item["role"] for item in body["items"]}
    assert roles == {"Despacho": "OWNER", "Clínica": "ACCOUNTANT"}


def test_figures_match_the_dashboard(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente Uno"}).json()
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura F-1",
            "amount": "2320",
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "category_id": _category(client, headers, "INCOME", "Ventas")["id"],
        },
    )
    assert receivable.status_code == 201, receivable.text

    item = _portfolio(client, owner)["items"][0]
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(item["cash"]) == Decimal(str(summary["cash"])) == Decimal("10000")
    assert Decimal(item["receivable"]) == Decimal(str(summary["receivables"])) == Decimal("2320")


def test_a_new_company_is_green(client):
    owner = register(client, initial_cash="10000")
    item = _portfolio(client, owner)["items"][0]
    assert item["status"] == "green"
    assert item["reasons"] == []
    assert item["last_closed_period"] is None


def test_overdue_payables_turn_the_company_red(client):
    owner = register(client, initial_cash="10000")
    _overdue_payable(client, auth_headers(owner))

    item = _portfolio(client, owner)["items"][0]
    assert Decimal(item["payable_overdue"]) == Decimal("4000")
    assert item["status"] == "red"
    assert item["reasons"] == ["$4,000.00 por pagar vencidos"]


def test_a_partial_payment_leaves_only_the_balance_overdue(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    payable = _overdue_payable(client, headers)
    account = client.get("/api/accounts", headers=headers).json()[0]
    paid = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "1500", "financial_account_id": account["id"]},
    )
    assert paid.status_code == 200, paid.text

    item = _portfolio(client, owner)["items"][0]
    assert Decimal(item["payable_overdue"]) == Decimal("2500")


def test_a_cancelled_payable_is_not_overdue(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    payable = _overdue_payable(client, headers)
    cancelled = client.post(
        f"/api/payables/{payable['id']}/cancel", headers=headers, json={"reason": "Duplicada"}
    )
    assert cancelled.status_code == 200, cancelled.text

    item = _portfolio(client, owner)["items"][0]
    assert Decimal(item["payable_overdue"]) == Decimal("0")
    assert item["status"] == "green"


def test_an_open_previous_month_flags_the_company(client):
    owner = register(client, initial_cash="10000")
    _income_last_month(client, auth_headers(owner))

    item = _portfolio(client, owner)["items"][0]
    assert item["previous_month_closed"] is False
    assert item["status"] == ("red" if date.today().day > 17 else "amber")
    assert len(item["reasons"]) == 1
    assert item["reasons"][0].endswith("sigue sin cerrar")


def test_closing_the_month_clears_the_flag(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    _income_last_month(client, headers)
    year, month = _previous_month()
    closed = client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})
    assert closed.status_code == 200, closed.text

    item = _portfolio(client, owner)["items"][0]
    assert item["previous_month_closed"] is True
    assert item["last_closed_period"] == f"{year}-{month:02d}"
    assert item["status"] == "green"


def test_a_reopened_month_counts_as_open_again(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    _income_last_month(client, headers)
    year, month = _previous_month()
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})
    reopened = client.post(
        "/api/periods/reopen",
        headers=headers,
        json={"year": year, "month": month, "reason": "Faltó una factura"},
    )
    assert reopened.status_code == 200, reopened.text

    item = _portfolio(client, owner)["items"][0]
    assert item["previous_month_closed"] is False
    assert item["last_closed_period"] is None
    assert item["status"] != "green"


def test_pending_proposals_show_up(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    key = client.post(
        "/api/agent-keys", headers=headers, json={"name": "Agente", "scopes": "READ,PROPOSE"}
    ).json()
    proposed = client.post(
        "/api/agent/invoke",
        headers={"Authorization": f"Bearer {key['token']}"},
        json={
            "tool": "propose_expense",
            "arguments": {
                "date": date.today().isoformat(),
                "description": "Cargo por identificar",
                "amount": "999",
                "category_id": _category(client, headers, "EXPENSE", "Otros")["id"],
                "summary": "Cargo no identificado en el banco",
            },
        },
    ).json()
    assert proposed["ok"] is True, proposed

    item = _portfolio(client, owner)["items"][0]
    assert item["pending_proposals"] == 1
    assert item["status"] == "amber"
    assert item["reasons"] == ["1 propuesta por revisar"]


def test_urgent_companies_come_first(client):
    contador = register(client, email="contador@example.com", business="Abarrotes Al Corriente")
    owner = register(client, email="duena@example.com", business="Zapatería Con Vencidos")
    owner_headers = auth_headers(owner)
    _overdue_payable(client, owner_headers)
    _invite(client, owner_headers, "contador@example.com")

    items = _portfolio(client, contador)["items"]
    assert [(item["name"], item["status"]) for item in items] == [
        ("Zapatería Con Vencidos", "red"),
        ("Abarrotes Al Corriente", "green"),
    ]
