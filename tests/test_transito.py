"""Dinero en tránsito: un procesador de pagos (NetPay) guarda cobros que aún
no llegan al banco. Son activo, no disponible; se liquidan al banco por el
neto y la comisión es un gasto financiero."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com", initial_cash="10000"):
    body = register(client, email=email, initial_cash=initial_cash)
    headers = auth_headers(body)
    caja = client.get("/api/accounts", headers=headers).json()[0]
    banco = client.post(
        "/api/accounts", headers=headers, json={"name": "BBVA", "type": "BANK", "opening_balance": "5000"}
    ).json()
    netpay = client.post(
        "/api/accounts",
        headers=headers,
        json={
            "name": "NetPay",
            "type": "PROCESSOR",
            "fee_rate": "0.035",
            "settlement_days": 2,
            "settlement_account_id": banco["id"],
        },
    ).json()
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    return headers, caja, banco, netpay, ventas


def _account(client, headers, account_id):
    return client.get(f"/api/accounts/{account_id}", headers=headers).json()


def _balances(client, headers):
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in report["rows"]}


def _card_sale(client, headers, ventas, amount="1000", account_id=None, payment_method="TARJETA_DEBITO"):
    payload = {
        "date": date.today().isoformat(),
        "description": "Venta con tarjeta",
        "amount": amount,
        "category_id": ventas["id"],
        "status": "PAID",
        "payment_method": payment_method,
    }
    if account_id:
        payload["financial_account_id"] = account_id
    return client.post("/api/income", headers=headers, json=payload)


def _settle(client, headers, netpay, gross="1000", fee="35", **extra):
    return client.post(
        f"/api/accounts/{netpay['id']}/settlements",
        headers=headers,
        json={"date": date.today().isoformat(), "gross_amount": gross, "fee_amount": fee, **extra},
    )


# --- Tipo PROCESSOR -------------------------------------------------------------


def test_processor_account_is_asset_but_not_available(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    assert netpay["type"] == "PROCESSOR"
    assert netpay["available"] is False
    assert netpay["is_liability"] is False
    assert netpay["fee_rate"] == "0.0350"
    assert netpay["settlement_days"] == 2
    assert netpay["settlement_account_id"] == banco["id"]
    assert caja["available"] is True


def test_card_sale_lands_in_processor_and_counts_as_in_transit(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    response = _card_sale(client, headers, ventas, account_id=netpay["id"])
    assert response.status_code == 201, response.text

    assert _account(client, headers, netpay["id"])["current_balance"] == "1000.00"
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    # Disponible: caja 10,000 + banco 5,000. NetPay no entra; va aparte.
    assert Decimal(str(summary["cash"])) == Decimal("15000")
    assert Decimal(str(summary["in_transit_total"])) == Decimal("1000")

    # La póliza es la de siempre, pero el cargo cae en la cuenta de tránsito.
    balances = _balances(client, headers)
    assert balances["1110"] == Decimal("1000")
    assert balances["1100"] == Decimal("15000")
    assert balances["4100"] == Decimal("1000")


def test_card_income_without_account_defaults_to_processor(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    response = _card_sale(client, headers, ventas, payment_method="TARJETA_CREDITO")
    assert response.status_code == 201, response.text
    assert response.json()["financial_account_id"] == netpay["id"]
    assert _account(client, headers, netpay["id"])["current_balance"] == "1000.00"


def test_card_income_without_processor_still_needs_an_account(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    response = _card_sale(client, headers, ventas)
    assert response.status_code == 400
    assert "cuenta" in response.json()["detail"].lower()


def test_in_transit_ledger_account_is_module_controlled(client):
    headers, *_ = _setup(client)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    transit = next(a for a in accounts if a["code"] == "1110")
    assert transit["name"] == "Cobros en tránsito"
    response = client.post(
        "/api/accounting/journal-entries",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "A mano",
            "lines": [
                {"account_id": transit["id"], "debit": "100", "credit": "0"},
                {"account_id": next(a for a in accounts if a["code"] == "3100")["id"], "debit": "0", "credit": "100"},
            ],
        },
    )
    assert response.status_code == 400
    assert "1110" in response.json()["detail"]


def test_settlement_bank_must_be_a_bank_of_the_same_company(client):
    headers, caja, banco, netpay, ventas = _setup(client)
    response = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "Mercado Pago", "type": "PROCESSOR", "settlement_account_id": caja["id"]},
    )
    assert response.status_code == 400
    assert "banco" in response.json()["detail"].lower()

    other = auth_headers(register(client, email="otra@example.com", initial_cash="0"))
    response = client.post(
        "/api/accounts",
        headers=other,
        json={"name": "Mercado Pago", "type": "PROCESSOR", "settlement_account_id": banco["id"]},
    )
    assert response.status_code == 400


def test_cash_series_adds_in_transit_only_with_processors(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    assert "in_transit" not in client.get("/api/reports/cash-series", headers=headers).json()

    headers, caja, banco, netpay, ventas = _setup(client, email="lafe@example.com")
    _card_sale(client, headers, ventas, account_id=netpay["id"])
    series = client.get("/api/reports/cash-series", headers=headers).json()
    assert Decimal(str(series["in_transit"][-1]["balance"])) == Decimal("1000")
    assert Decimal(str(series["points"][-1]["balance"])) == Decimal("15000")
