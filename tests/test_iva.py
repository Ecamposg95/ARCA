"""IVA por flujo de efectivo: se causa al cobrar/pagar, no al facturar."""

from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    renta = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Renta"
    )
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente IVA"}).json()
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Proveedor IVA"}).json()
    return headers, account, ventas, renta, customer, vendor


def _balances(client, headers):
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in report["rows"]}


def test_breakdown_is_exact(client):
    headers, account, ventas, _renta, _c, _v = _setup(client)
    income = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta con IVA",
            "amount": "1160",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    assert Decimal(income["subtotal"]) == Decimal("1000.00")
    assert Decimal(income["tax_amount"]) == Decimal("160.00")
    # El desglose siempre reconstruye el total exacto.
    assert Decimal(income["subtotal"]) + Decimal(income["tax_amount"]) == Decimal(income["amount"])


def test_paid_income_credits_collected_vat(client):
    headers, account, ventas, _renta, _c, _v = _setup(client)
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta",
            "amount": "1160",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    balances = _balances(client, headers)
    assert balances["4100"] == Decimal("1000")  # ingreso sin IVA
    assert balances["2190"] == Decimal("160")  # IVA trasladado cobrado
    assert balances["1100"] == Decimal("101160")  # el efectivo sí recibe el total


def test_paid_expense_debits_creditable_vat(client):
    headers, account, _ventas, renta, _c, _v = _setup(client)
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Renta",
            "amount": "1160",
            "tax_rate": "0.16",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    balances = _balances(client, headers)
    assert balances["5300"] == Decimal("1000")
    assert balances["1190"] == Decimal("160")


def test_receivable_vat_is_pending_until_collected(client):
    headers, account, ventas, _renta, customer, _v = _setup(client)
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura a crédito",
            "amount": "1160",
            "tax_rate": "0.16",
            "due_date": "2026-09-30",
            "category_id": ventas["id"],
        },
    ).json()

    # Emitida: el IVA existe pero NO se declara todavía.
    balances = _balances(client, headers)
    assert balances["2191"] == Decimal("160")
    assert balances.get("2190", Decimal("0")) == Decimal("0")

    # Cobro de la mitad: la mitad del IVA se vuelve declarable.
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "580", "financial_account_id": account["id"]},
    )
    balances = _balances(client, headers)
    assert balances["2190"] == Decimal("80")
    assert balances["2191"] == Decimal("80")

    # Al liquidar, el pendiente cierra exactamente en cero.
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "580", "financial_account_id": account["id"]},
    )
    balances = _balances(client, headers)
    assert balances["2190"] == Decimal("160")
    assert balances.get("2191", Decimal("0")) == Decimal("0")


def test_payable_vat_becomes_creditable_when_paid(client):
    headers, account, _ventas, renta, _c, vendor = _setup(client)
    payable = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Servicio a crédito",
            "amount": "2320",
            "tax_rate": "0.16",
            "due_date": "2026-09-30",
            "category_id": renta["id"],
        },
    ).json()
    balances = _balances(client, headers)
    assert balances["1191"] == Decimal("320")

    client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "2320", "financial_account_id": account["id"]},
    )
    balances = _balances(client, headers)
    assert balances["1190"] == Decimal("320")
    assert balances.get("1191", Decimal("0")) == Decimal("0")


def test_zero_rate_produces_the_previous_entry(client):
    headers, account, ventas, _renta, _c, _v = _setup(client)
    income = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta exenta",
            "amount": "1000",
            "tax_rate": "0",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    assert Decimal(income["tax_amount"]) == Decimal("0")
    balances = _balances(client, headers)
    assert balances["4100"] == Decimal("1000")
    assert "2190" not in balances  # sin línea de IVA


def test_vat_report_matches_ledger(client):
    headers, account, ventas, renta, _c, _v = _setup(client)
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta",
            "amount": "11600",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": "2026-08-12",
            "description": "Renta",
            "amount": "4640",
            "tax_rate": "0.16",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    report = client.get("/api/reports/iva?start=2026-08-01&end=2026-08-31", headers=headers).json()
    assert Decimal(str(report["vat_charged"])) == Decimal("1600")
    assert Decimal(str(report["vat_creditable"])) == Decimal("640")
    assert Decimal(str(report["to_pay"])) == Decimal("960")
    assert Decimal(str(report["in_favor"])) == Decimal("0")


def test_trial_balance_still_balances_with_vat(client):
    headers, account, ventas, renta, customer, vendor = _setup(client)
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta",
            "amount": "1160",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Crédito",
            "amount": "2320",
            "tax_rate": "0.16",
            "due_date": "2026-09-30",
            "category_id": ventas["id"],
        },
    )
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(report["total_debit"])) == Decimal(str(report["total_credit"]))
    balance = client.get("/api/reports/balance-sheet?as_of=2026-12-31", headers=headers).json()
    assert balance["balanced"] is True
