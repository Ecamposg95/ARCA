"""Reversos: deshacer sin borrar. El original queda; la corrección también."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    renta = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Renta"
    )
    return headers, account, ventas, renta


def _balance(client, headers) -> Decimal:
    return Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))


def _ledger_balanced(client, headers) -> bool:
    b = client.get("/api/accounting/trial-balance", headers=headers).json()
    return Decimal(str(b["total_debit"])) == Decimal(str(b["total_credit"]))


def test_reversing_a_paid_expense_returns_the_money(client):
    headers, account, _ventas, renta = _setup(client)
    before = _balance(client, headers)

    expense = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Gasto equivocado",
            "amount": "11600",
            "tax_rate": "0.16",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    assert _balance(client, headers) == before - Decimal("11600")

    response = client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})
    assert response.status_code == 200

    assert _balance(client, headers) == before
    assert _ledger_balanced(client, headers)


def test_the_original_entry_is_not_deleted(client):
    headers, account, _ventas, renta = _setup(client)
    expense = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Gasto equivocado",
            "amount": "5000",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})

    entries = client.get(
        f"/api/accounting/journal-entries?source_type=expense&source_id={expense['id']}",
        headers=headers,
    ).json()["items"]
    # Dos pólizas: la original y su espejo. Un auditor ve ambas.
    assert len(entries) == 2
    assert any(e["description"].startswith("Reverso:") for e in entries)


def test_reversing_a_partially_collected_receivable(client):
    headers, account, ventas, _renta = _setup(client)
    before = _balance(client, headers)

    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": client.post(
                "/api/customers", headers=headers, json={"name": "Cliente"}
            ).json()["id"],
            "description": "Factura mal emitida",
            "amount": "23200",
            "tax_rate": "0.16",
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "category_id": ventas["id"],
        },
    ).json()
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "11600", "financial_account_id": account["id"]},
    )
    assert _balance(client, headers) == before + Decimal("11600")

    response = client.post(f"/api/receivables/{receivable['id']}/cancel", headers=headers, json={})
    assert response.status_code == 200, response.text

    # Se revierten el registro Y el cobro: el dinero se va, la cuenta desaparece.
    assert _balance(client, headers) == before
    assert _ledger_balanced(client, headers)


def test_reversing_twice_is_rejected(client):
    headers, account, _ventas, renta = _setup(client)
    expense = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Gasto",
            "amount": "1000",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})
    again = client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})
    assert again.status_code == 400


def test_a_reversal_shows_up_as_its_own_movement_type(client):
    headers, account, ventas, _renta = _setup(client)
    income = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta",
            "amount": "3000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    client.post(f"/api/income/{income['id']}/cancel", headers=headers, json={})

    movements = client.get("/api/transactions", headers=headers).json()["items"]
    # Un reverso no se disfraza de gasto: tiene su propio tipo.
    assert any(m["transaction_type"] == "REVERSAL_OUT" for m in movements)
    assert not any(m["transaction_type"] == "EXPENSE" for m in movements)


def test_a_card_expense_reversal_lowers_the_debt(client):
    headers, _account, _ventas, renta = _setup(client)
    card = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "AMEX", "type": "CREDIT_CARD", "credit_limit": "50000"},
    ).json()
    expense = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Compra con tarjeta",
            "amount": "8000",
            "category_id": renta["id"],
            "financial_account_id": card["id"],
            "status": "PAID",
        },
    ).json()
    assert Decimal(str(client.get("/api/dashboard/summary", headers=headers).json()["card_debt"])) == Decimal("8000")

    client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})
    # La deuda baja, no sube: el reverso respeta la naturaleza del instrumento.
    assert Decimal(str(client.get("/api/dashboard/summary", headers=headers).json()["card_debt"])) == Decimal("0")


def test_a_reversal_cannot_land_in_a_closed_month(client):
    headers, account, _ventas, renta = _setup(client)
    closed_end = date.today().replace(day=1) - timedelta(days=1)

    expense = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": closed_end.isoformat(),
            "description": "Gasto del mes pasado",
            "amount": "2000",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    client.post(
        "/api/periods/close",
        headers=headers,
        json={"year": closed_end.year, "month": closed_end.month},
    )

    # El reverso se fecha HOY, que sigue abierto: cerrar el mes pasado no
    # impide corregir hacia adelante, que es justo lo correcto.
    response = client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})
    assert response.status_code == 200
    assert _ledger_balanced(client, headers)
