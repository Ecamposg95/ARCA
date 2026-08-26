"""Deducibilidad: avisar a tiempo, no bloquear (LISR 27-III)."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="100000")
    headers = auth_headers(body)
    caja = next(a for a in client.get("/api/accounts", headers=headers).json() if a["type"] == "CASH")
    banco = client.post(
        "/api/accounts", headers=headers, json={"name": "BBVA", "type": "BANK"}
    ).json()
    renta = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Renta"
    )
    return headers, caja, banco, renta


def _expense(client, headers, account, categoria, amount):
    return client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Gasto",
            "amount": amount,
            "category_id": categoria["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()


def test_cash_over_the_limit_warns(client):
    headers, caja, _banco, renta = _setup(client)
    expense = _expense(client, headers, caja, renta, "2500")
    assert expense["payment_method"] == "EFECTIVO"
    assert "no será deducible" in expense["deductibility_warning"]


def test_cash_under_the_limit_does_not_warn(client):
    headers, caja, _banco, renta = _setup(client)
    expense = _expense(client, headers, caja, renta, "1800")
    assert expense["deductibility_warning"] is None


def test_the_limit_itself_is_still_deductible(client):
    headers, caja, _banco, renta = _setup(client)
    assert _expense(client, headers, caja, renta, "2000")["deductibility_warning"] is None


def test_a_transfer_never_warns(client):
    headers, _caja, banco, renta = _setup(client)
    expense = _expense(client, headers, banco, renta, "500000")
    assert expense["payment_method"] == "TRANSFERENCIA"
    assert expense["deductibility_warning"] is None


def test_the_warning_does_not_block_the_expense(client):
    headers, caja, _banco, renta = _setup(client)
    before = Decimal(str(client.get(f"/api/accounts/{caja['id']}", headers=headers).json()["current_balance"]))
    expense = _expense(client, headers, caja, renta, "9000")
    after = Decimal(str(client.get(f"/api/accounts/{caja['id']}", headers=headers).json()["current_balance"]))

    # El gasto es real y se registra: avisar no es impedir.
    assert expense["status"] == "PAID"
    assert before - after == Decimal("9000")
