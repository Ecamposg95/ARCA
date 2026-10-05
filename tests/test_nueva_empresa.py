"""Alta de otra empresa: el contador suma un cliente sin cerrar sesión."""

from decimal import Decimal

from tests.helpers import auth_headers, register


def _bearer(auth_body: dict) -> dict:
    return {"Authorization": f"Bearer {auth_body['access_token']}"}


def _create(client, auth_body: dict, **payload):
    payload.setdefault("business_name", "Cliente Nuevo")
    return client.post("/api/organizations", headers=_bearer(auth_body), json=payload)


def _headers_for(auth_body: dict, organization_id: str) -> dict:
    return {**_bearer(auth_body), "X-Organization-ID": organization_id}


def test_requires_a_session(client):
    response = client.post("/api/organizations", json={"business_name": "Sin sesión"})
    assert response.status_code == 401


def test_a_signed_in_user_opens_a_second_company(client):
    contador = register(client, email="contador@example.com", business="Despacho")

    response = _create(client, contador, business_name="  Ferretería El Tornillo ", tax_id=" fet180312ab1 ")
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == "Ferretería El Tornillo"
    assert created["tax_id"] == "FET180312AB1"

    portfolio = client.get("/api/portfolio", headers=_bearer(contador)).json()
    roles = {item["name"]: item["role"] for item in portfolio["items"]}
    assert roles == {"Despacho": "OWNER", "Ferretería El Tornillo": "OWNER"}


def test_the_new_company_is_born_with_its_books(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    created = _create(client, contador, initial_cash="2500").json()
    headers = _headers_for(contador, created["id"])

    assert len(client.get("/api/accounting/accounts", headers=headers).json()) > 0
    assert len(client.get("/api/categories?kind=EXPENSE", headers=headers).json()) > 0

    accounts = client.get("/api/accounts", headers=headers).json()
    assert [(a["name"], a["current_balance"]) for a in accounts] == [("Caja", "2500.00")]

    # El saldo inicial entró por el motor contable: la balanza cuadra.
    balanza = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balanza["total_debit"])) == Decimal(str(balanza["total_credit"])) == Decimal("2500")


def test_the_new_company_does_not_touch_the_first_one(client):
    contador = register(client, email="contador@example.com", business="Despacho", initial_cash="10000")
    created = _create(client, contador, initial_cash="2500").json()

    first = client.get("/api/accounts", headers=auth_headers(contador)).json()
    assert [a["current_balance"] for a in first] == ["10000.00"]

    # Otra persona no entra a la empresa nueva aunque conozca su identificador.
    intruso = register(client, email="intruso@example.com", business="Otra")
    response = client.get("/api/accounts", headers=_headers_for(intruso, created["id"]))
    assert response.status_code == 403


def test_a_blank_name_is_rejected(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    assert _create(client, contador, business_name="   ").status_code == 422
    assert client.get("/api/portfolio", headers=_bearer(contador)).json()["total"] == 1


def test_a_negative_opening_balance_is_rejected(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    assert _create(client, contador, initial_cash="-1").status_code == 422
