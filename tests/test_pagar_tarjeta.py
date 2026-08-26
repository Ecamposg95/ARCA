"""Pagar la tarjeta: un traspaso banco→tarjeta baja la deuda sin duplicar gasto."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="100000")
    headers = auth_headers(body)
    bank = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "BBVA", "type": "BANK", "opening_balance": "50000"},
    ).json()
    card = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "AMEX", "type": "CREDIT_CARD", "credit_limit": "80000"},
    ).json()
    software = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Software"
    )
    # El gasto que creó la deuda: licencias pagadas con la tarjeta.
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Licencias del equipo",
            "amount": "11600",
            "tax_rate": "0.16",
            "category_id": software["id"],
            "financial_account_id": card["id"],
            "status": "PAID",
        },
    )
    return headers, bank, card


def _account(client, headers, account_id):
    return client.get(f"/api/accounts/{account_id}", headers=headers).json()


def test_paying_the_card_lowers_debt_and_bank(client):
    headers, bank, card = _setup(client)
    assert Decimal(str(_account(client, headers, card["id"])["current_balance"])) == Decimal("11600")

    response = client.post(
        "/api/transactions/transfer",
        headers=headers,
        json={
            "from_account_id": bank["id"],
            "to_account_id": card["id"],
            "amount": "11600",
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text

    # La deuda queda en cero y el banco bajó exactamente lo pagado.
    assert Decimal(str(_account(client, headers, card["id"])["current_balance"])) == Decimal("0")
    assert Decimal(str(_account(client, headers, bank["id"])["current_balance"])) == Decimal("38400")


def test_paying_the_card_does_not_duplicate_the_expense(client):
    headers, bank, card = _setup(client)
    pl_before = client.get("/api/reports/profit-loss", headers=headers).json()

    client.post(
        "/api/transactions/transfer",
        headers=headers,
        json={
            "from_account_id": bank["id"],
            "to_account_id": card["id"],
            "amount": "11600",
            "date": date.today().isoformat(),
        },
    )

    # Pagar la tarjeta NO es un gasto nuevo: el gasto ya se reconoció al comprar.
    pl_after = client.get("/api/reports/profit-loss", headers=headers).json()
    assert Decimal(str(pl_after["total_expenses"])) == Decimal(str(pl_before["total_expenses"]))

    expenses = client.get("/api/expenses", headers=headers).json()
    assert expenses["total"] == 1  # sigue habiendo un solo gasto

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balance["total_debit"])) == Decimal(str(balance["total_credit"]))


def test_the_payment_description_says_what_it_is(client):
    headers, bank, card = _setup(client)
    rows = client.post(
        "/api/transactions/transfer",
        headers=headers,
        json={
            "from_account_id": bank["id"],
            "to_account_id": card["id"],
            "amount": "5000",
            "date": date.today().isoformat(),
        },
    ).json()
    assert all("Pago de AMEX" in row["description"] for row in rows)
