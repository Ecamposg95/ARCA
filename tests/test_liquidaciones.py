"""Liquidaciones de un procesador: el bruto sale del procesador, el neto llega
al banco y la comisión es un gasto. Nunca se duplica el cobro."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register
from tests.test_transito import _account, _balances, _card_sale, _settle, _setup


def test_settlement_moves_net_to_bank_and_fee_to_results(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    _card_sale(client, headers, ventas, account_id=netpay["id"], amount="1000")
    before = _balances(client, headers)

    response = _settle(client, headers, netpay, gross="1000", fee="35", reference="NP-0001")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["net_amount"] == "965.00"
    assert body["bank_account_id"] == banco["id"]  # el banco configurado en el procesador
    assert body["expense_id"] is not None

    # Procesador −bruto, banco +neto, y el cobro no se duplica en ingresos.
    assert _account(client, headers, netpay["id"])["current_balance"] == "0.00"
    assert _account(client, headers, banco["id"])["current_balance"] == "5965.00"
    after = _balances(client, headers)
    assert after["1110"] == Decimal("0")
    assert after["1100"] - before["1100"] == Decimal("965")
    assert after["5700"] - before.get("5700", Decimal("0")) == Decimal("35")
    assert after["4100"] == before["4100"]
    trial = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))

    # El gasto de comisión quedó con su categoría sembrada.
    categories = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    assert any(c["name"] == "Comisiones de terminal" for c in categories)

    page = client.get(f"/api/accounts/{netpay['id']}/settlements", headers=headers).json()
    assert page["total"] == 1 and page["items"][0]["reference"] == "NP-0001"


def test_settlement_without_fee_creates_no_expense(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    _card_sale(client, headers, ventas, account_id=netpay["id"], amount="500")
    response = _settle(client, headers, netpay, gross="500", fee="0")
    assert response.status_code == 201, response.text
    assert response.json()["expense_id"] is None
    assert _account(client, headers, banco["id"])["current_balance"] == "5500.00"


def test_settlement_validations(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    _card_sale(client, headers, ventas, account_id=netpay["id"], amount="1000")

    # Bruto mayor al saldo del procesador.
    response = _settle(client, headers, netpay, gross="1200", fee="10")
    assert response.status_code == 400
    assert "$1,000.00" in response.json()["detail"]

    # Referencia repetida.
    assert _settle(client, headers, netpay, gross="400", fee="10", reference="NP-1").status_code == 201
    response = _settle(client, headers, netpay, gross="100", fee="1", reference="NP-1")
    assert response.status_code == 409
    assert "ya está registrada" in response.json()["detail"]

    # El destino debe ser banco.
    response = _settle(client, headers, netpay, gross="100", fee="1", bank_account_id=caja["id"])
    assert response.status_code == 400

    # Sólo un procesador liquida.
    response = client.post(
        f"/api/accounts/{banco['id']}/settlements",
        headers=headers,
        json={"date": date.today().isoformat(), "gross_amount": "10", "fee_amount": "0"},
    )
    assert response.status_code == 400


def test_settlement_without_configured_bank_asks_for_one(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    mp = client.post("/api/accounts", headers=headers, json={"name": "Mercado Pago", "type": "PROCESSOR"}).json()
    _card_sale(client, headers, ventas, account_id=mp["id"], amount="300")
    response = _settle(client, headers, mp, gross="300", fee="9")
    assert response.status_code == 400
    assert response.json()["detail"] == "Elige el banco donde liquida."


def test_cancelling_a_settlement_reverses_transfer_and_fee(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    _card_sale(client, headers, ventas, account_id=netpay["id"], amount="1000")
    before = _balances(client, headers)
    settlement = _settle(client, headers, netpay, gross="1000", fee="35", reference="NP-2").json()

    url = f"/api/accounts/{netpay['id']}/settlements/{settlement['id']}"
    response = client.delete(url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"

    assert _account(client, headers, netpay["id"])["current_balance"] == "1000.00"
    assert _account(client, headers, banco["id"])["current_balance"] == "5000.00"
    after = _balances(client, headers)
    assert after["1110"] == before["1110"]
    assert after["1100"] == before["1100"]
    assert after.get("5700", Decimal("0")) == before.get("5700", Decimal("0"))
    # Dos veces, no.
    assert client.delete(url, headers=headers).status_code == 400
    # La referencia queda libre para registrarla bien.
    assert _settle(client, headers, netpay, gross="1000", fee="35", reference="NP-2").status_code == 201


def _member_headers(client, headers, email="cajero@example.com", role="MEMBER"):
    """Invita a alguien con `role` y devuelve sus encabezados."""
    response = client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": email, "name": "Cajero", "role": role, "password": "supersegura123"},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={"email": email, "password": "supersegura123"}).json()
    return {"Authorization": f"Bearer {login['access_token']}", "X-Organization-ID": headers["X-Organization-ID"]}


def test_settlements_need_admin_and_respect_tenant(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    _card_sale(client, headers, ventas, account_id=netpay["id"], amount="1000")
    member = _member_headers(client, headers)
    assert _settle(client, member, netpay).status_code == 403

    other = auth_headers(register(client, email="otra@example.com", initial_cash="0"))
    assert client.get(f"/api/accounts/{netpay['id']}/settlements", headers=other).status_code == 404
    assert _settle(client, other, netpay).status_code == 404
