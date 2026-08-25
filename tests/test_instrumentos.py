"""Instrumentos: una tarjeta de crédito registra deuda, no dinero disponible."""

from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    caja = client.get("/api/accounts", headers=headers).json()[0]
    software = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Software"
    )
    tarjeta = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "AMEX Empresarial", "type": "CREDIT_CARD", "credit_limit": "50000"},
    ).json()
    return headers, caja, tarjeta, software


def _balances(client, headers):
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in report["rows"]}


def _spend_with_card(client, headers, tarjeta, software, amount="5000"):
    return client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": "2026-08-25",
            "description": "Licencias con tarjeta",
            "amount": amount,
            "category_id": software["id"],
            "financial_account_id": tarjeta["id"],
            "status": "PAID",
        },
    )


def test_card_expense_creates_debt_and_leaves_cash_intact(client):
    headers, caja, tarjeta, software = _setup(client)
    assert _spend_with_card(client, headers, tarjeta, software).status_code == 201

    # El efectivo NO se tocó: la compra no salió del banco.
    assert client.get(f"/api/accounts/{caja['id']}", headers=headers).json()["current_balance"] == "10000.00"
    # La tarjeta ahora debe.
    card = client.get(f"/api/accounts/{tarjeta['id']}", headers=headers).json()
    assert card["current_balance"] == "5000.00"
    assert card["is_liability"] is True
    assert Decimal(card["available_credit"]) == Decimal("45000")

    balances = _balances(client, headers)
    assert balances["1100"] == Decimal("10000")  # el efectivo intacto en la contabilidad
    assert balances["2200"] == Decimal("5000")  # la deuda existe y es visible
    assert balances["5400"] == Decimal("5000")  # el gasto se reconoció


def test_dashboard_available_excludes_card_debt(client):
    headers, _caja, tarjeta, software = _setup(client)
    _spend_with_card(client, headers, tarjeta, software)
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    # Disponible = sólo instrumentos de activo; la deuda se reporta aparte.
    assert Decimal(str(summary["cash"])) == Decimal("10000")
    assert Decimal(str(summary["card_debt"])) == Decimal("5000")


def test_paying_the_card_reduces_debt_without_double_counting(client):
    headers, caja, tarjeta, software = _setup(client)
    _spend_with_card(client, headers, tarjeta, software)

    response = client.post(
        "/api/transactions/transfer",
        headers=headers,
        json={
            "from_account_id": caja["id"],
            "to_account_id": tarjeta["id"],
            "amount": "5000",
            "date": "2026-08-26",
        },
    )
    assert response.status_code == 201, response.text

    assert client.get(f"/api/accounts/{caja['id']}", headers=headers).json()["current_balance"] == "5000.00"
    assert client.get(f"/api/accounts/{tarjeta['id']}", headers=headers).json()["current_balance"] == "0.00"

    balances = _balances(client, headers)
    assert balances["1100"] == Decimal("5000")
    assert balances.get("2200", Decimal("0")) == Decimal("0")
    # El gasto sigue siendo UNO: pagar la tarjeta no vuelve a gastar.
    assert balances["5400"] == Decimal("5000")


def test_card_opening_balance_is_debt_not_money(client):
    body = register(client, initial_cash="1000")
    headers = auth_headers(body)
    client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "Tarjeta con deuda previa", "type": "CREDIT_CARD", "opening_balance": "3000"},
    )
    balances = _balances(client, headers)
    assert balances["2200"] == Decimal("3000")  # deuda
    assert balances["1100"] == Decimal("1000")  # el efectivo no creció
    # La deuda inicial reduce el capital: no apareció dinero de la nada.
    assert balances["3100"] == Decimal("-2000")


def test_payment_method_is_recorded(client):
    headers, caja, tarjeta, software = _setup(client)
    _spend_with_card(client, headers, tarjeta, software)
    movements = client.get(f"/api/transactions?account_id={tarjeta['id']}", headers=headers).json()
    assert movements["items"][0]["payment_method"] == "TARJETA_CREDITO"

    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": "2026-08-25",
            "description": "Compra en efectivo",
            "amount": "300",
            "category_id": software["id"],
            "financial_account_id": caja["id"],
            "status": "PAID",
        },
    )
    movements = client.get(f"/api/transactions?account_id={caja['id']}", headers=headers).json()
    assert movements["items"][0]["payment_method"] == "EFECTIVO"


def test_balance_sheet_shows_the_card_as_liability(client):
    headers, _caja, tarjeta, software = _setup(client)
    _spend_with_card(client, headers, tarjeta, software)
    report = client.get("/api/reports/balance-sheet?as_of=2026-12-31", headers=headers).json()
    assert report["balanced"] is True
    liabilities = {row["code"]: Decimal(str(row["amount"])) for row in report["liabilities"]}
    assert liabilities["2200"] == Decimal("5000")
