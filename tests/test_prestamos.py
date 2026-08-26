"""Préstamos: pagar un crédito no es gasto. Sólo el interés lo es."""

from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    return headers, account


def _create_loan(client, headers, account, **overrides):
    payload = {
        "lender": "BBVA",
        "description": "Crédito para capital de trabajo",
        "principal": "120000",
        "annual_rate": "0.24",
        "term_months": 12,
        "start_date": "2026-01-01",
        "financial_account_id": account["id"],
    }
    payload.update(overrides)
    response = client.post("/api/loans", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_receiving_a_loan_is_cash_and_debt_not_income(client):
    headers, account = _setup(client)
    _create_loan(client, headers, account)

    accounts = client.get("/api/accounts", headers=headers).json()
    assert Decimal(str(accounts[0]["current_balance"])) == Decimal("220000")

    # Un préstamo no es venta: el resultado del periodo no se mueve.
    pl = client.get("/api/reports/profit-loss", headers=headers).json()
    assert Decimal(str(pl["total_revenue"])) == Decimal("0")

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    credits = {row["code"]: Decimal(str(row["credit"])) for row in balance["rows"]}
    assert credits.get("2300") == Decimal("120000")


def test_payment_splits_principal_from_interest(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account)

    # 24% anual sobre 120,000 = 2,400 de interés el primer mes.
    payment = client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "11400", "financial_account_id": account["id"], "date": "2026-02-01"},
    ).json()

    assert Decimal(str(payment["interest_part"])) == Decimal("2400")
    assert Decimal(str(payment["principal_part"])) == Decimal("9000")

    # Sólo el interés llega al estado de resultados.
    pl = client.get(
        "/api/reports/profit-loss?start=2026-02-01&end=2026-02-28", headers=headers
    ).json()
    assert Decimal(str(pl["total_expenses"])) == Decimal("2400")


def test_payment_lowers_the_outstanding_debt(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account)
    client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "11400", "financial_account_id": account["id"], "date": "2026-02-01"},
    )
    updated = client.get("/api/loans", headers=headers).json()["items"][0]
    assert Decimal(str(updated["outstanding"])) == Decimal("111000")
    assert Decimal(str(updated["paid_principal"])) == Decimal("9000")


def test_a_payment_that_does_not_cover_interest_is_rejected(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account)
    response = client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "1000", "financial_account_id": account["id"], "date": "2026-02-01"},
    )
    assert response.status_code == 400
    assert "intereses" in response.json()["detail"]


def test_schedule_ends_exactly_at_zero(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account)
    schedule = client.get(f"/api/loans/{loan['id']}/schedule", headers=headers).json()

    assert len(schedule["rows"]) == 12
    assert Decimal(str(schedule["rows"][-1]["balance"])) == Decimal("0")
    # El capital de toda la tabla suma exactamente el préstamo.
    total_principal = sum(Decimal(str(row["principal"])) for row in schedule["rows"])
    assert total_principal == Decimal("120000")


def test_schedule_without_interest_is_the_principal_split_evenly(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account, annual_rate="0", principal="12000", term_months=12)
    schedule = client.get(f"/api/loans/{loan['id']}/schedule", headers=headers).json()
    assert Decimal(str(schedule["monthly_payment"])) == Decimal("1000")
    assert all(Decimal(str(row["interest"])) == Decimal("0") for row in schedule["rows"])


def test_paying_it_off_marks_the_loan_as_paid(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account, principal="10000", annual_rate="0", term_months=2)
    client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "10000", "financial_account_id": account["id"], "date": "2026-02-01"},
    )
    updated = client.get("/api/loans", headers=headers).json()["items"][0]
    assert Decimal(str(updated["outstanding"])) == Decimal("0")
    assert updated["status"] == "PAID"


def test_cannot_pay_a_settled_loan(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account, principal="5000", annual_rate="0", term_months=1)
    client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "5000", "financial_account_id": account["id"], "date": "2026-02-01"},
    )
    response = client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "1000", "financial_account_id": account["id"], "date": "2026-03-01"},
    )
    assert response.status_code == 400


def test_ledger_balances_after_loan_and_payment(client):
    headers, account = _setup(client)
    loan = _create_loan(client, headers, account)
    client.post(
        f"/api/loans/{loan['id']}/pay",
        headers=headers,
        json={"amount": "11400", "financial_account_id": account["id"], "date": "2026-02-01"},
    )
    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balance["total_debit"])) == Decimal(str(balance["total_credit"]))


def test_loan_debt_shows_up_in_net_worth(client):
    headers, account = _setup(client)
    before = client.get("/api/reports/net-worth", headers=headers).json()
    _create_loan(client, headers, account)
    after = client.get("/api/reports/net-worth", headers=headers).json()

    # Entra dinero y nace deuda por el mismo monto: el patrimonio no cambia.
    assert Decimal(str(after["total_liabilities"])) == Decimal("120000")
    assert Decimal(str(after["net_worth"])) == Decimal(str(before["net_worth"]))


def test_loans_are_isolated_by_organization(client):
    headers_a, account_a = _setup(client)
    _create_loan(client, headers_a, account_a)
    headers_b, _account_b = _setup(client, email="otra@example.com")
    assert client.get("/api/loans", headers=headers_b).json()["items"] == []
