"""Retenciones: el impuesto que le descuentas al proveedor es deuda con el SAT."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    honorarios = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Honorarios"
    )
    return headers, account, honorarios


def _honorarios(client, headers, account, categoria, **extra):
    """Honorarios de 10,000 + IVA, con las retenciones de ley a persona física."""
    payload = {
        "date": date.today().isoformat(),
        "description": "Honorarios del despacho",
        "amount": "11600",
        "tax_rate": "0.16",
        "category_id": categoria["id"],
        "financial_account_id": account["id"],
        "status": "PAID",
    }
    payload.update(extra)
    response = client.post("/api/expenses", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_withholding_lowers_what_leaves_the_bank(client):
    headers, account, honorarios = _setup(client)
    before = Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))

    # 10% de ISR y dos terceras partes del IVA.
    _honorarios(
        client, headers, account, honorarios, retention_isr="1000", retention_iva="1066.67"
    )

    after = Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))
    # Factura 11,600 pero al proveedor sólo le llegan 9,533.33.
    assert before - after == Decimal("9533.33")


def test_what_is_withheld_becomes_a_liability(client):
    headers, account, honorarios = _setup(client)
    _honorarios(
        client, headers, account, honorarios, retention_isr="1000", retention_iva="1066.67"
    )

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    credits = {row["code"]: Decimal(str(row["credit"])) for row in balance["rows"]}
    assert credits.get("2400") == Decimal("1000")
    assert credits.get("2410") == Decimal("1066.67")


def test_the_expense_is_still_the_full_amount(client):
    headers, account, honorarios = _setup(client)
    _honorarios(
        client, headers, account, honorarios, retention_isr="1000", retention_iva="1066.67"
    )
    pl = client.get("/api/reports/profit-loss", headers=headers).json()
    # Retener no abarata el servicio: el gasto son los 10,000 completos.
    assert Decimal(str(pl["total_expenses"])) == Decimal("10000")


def test_withholding_lowers_net_worth_by_the_expense_only(client):
    headers, account, honorarios = _setup(client)
    before = client.get("/api/reports/net-worth", headers=headers).json()
    _honorarios(
        client, headers, account, honorarios, retention_isr="1000", retention_iva="1066.67"
    )
    after = client.get("/api/reports/net-worth", headers=headers).json()

    # El patrimonio baja por el gasto, no por lo retenido: eso sólo cambia de
    # acreedor, del proveedor al SAT.
    assert Decimal(str(before["net_worth"])) - Decimal(str(after["net_worth"])) == Decimal("10000")


def test_the_ledger_balances_with_withholdings(client):
    headers, account, honorarios = _setup(client)
    _honorarios(
        client, headers, account, honorarios, retention_isr="1000", retention_iva="1066.67"
    )
    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balance["total_debit"])) == Decimal(str(balance["total_credit"]))


def test_without_withholdings_nothing_changes(client):
    headers, account, honorarios = _setup(client)
    before = Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))
    _honorarios(client, headers, account, honorarios)
    after = Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))
    assert before - after == Decimal("11600")

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    codes = {row["code"] for row in balance["rows"]}
    # Sin retención no se ensucia el catálogo con cuentas en cero.
    assert "2400" not in codes and "2410" not in codes


def test_reversing_a_withheld_expense_undoes_the_liability(client):
    headers, account, honorarios = _setup(client)
    before = Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))
    expense = _honorarios(
        client, headers, account, honorarios, retention_isr="1000", retention_iva="1066.67"
    )

    client.post(f"/api/expenses/{expense['id']}/cancel", headers=headers, json={})

    after = Decimal(str(client.get("/api/accounts", headers=headers).json()[0]["current_balance"]))
    assert after == before

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    rows = {row["code"]: row for row in balance["rows"]}
    # La deuda con el SAT se cancela contra sí misma: cargo y abono iguales.
    if "2400" in rows:
        assert Decimal(str(rows["2400"]["debit"])) == Decimal(str(rows["2400"]["credit"]))
    assert Decimal(str(balance["total_debit"])) == Decimal(str(balance["total_credit"]))
