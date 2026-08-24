from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    renta = next(c for c in categories if c["name"] == "Renta")
    return headers, account, renta


def test_paid_expense_decreases_cash(client):
    headers, account, renta = _setup(client)
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": "2026-08-05",
            "description": "Renta de agosto",
            "amount": "3500",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "6500.00"


def test_transfer_moves_between_accounts(client):
    headers, caja, _renta = _setup(client)
    bank = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "BBVA Operativa", "type": "BANK", "opening_balance": "0"},
    ).json()
    response = client.post(
        "/api/transactions/transfer",
        headers=headers,
        json={
            "from_account_id": caja["id"],
            "to_account_id": bank["id"],
            "amount": "4000",
            "date": "2026-08-06",
        },
    )
    assert response.status_code == 201, response.text
    caja_balance = client.get(f"/api/accounts/{caja['id']}", headers=headers).json()["current_balance"]
    bank_balance = client.get(f"/api/accounts/{bank['id']}", headers=headers).json()["current_balance"]
    assert caja_balance == "6000.00"
    assert bank_balance == "4000.00"


def test_expense_requires_account_to_pay(client):
    headers, _account, renta = _setup(client)
    created = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": "2026-08-05",
            "description": "Luz",
            "amount": "800",
            "category_id": renta["id"],
        },
    ).json()
    response = client.post(f"/api/expenses/{created['id']}/pay", headers=headers, json={})
    assert response.status_code == 400
    assert "cuenta" in response.json()["detail"].lower()
