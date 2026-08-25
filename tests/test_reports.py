from decimal import Decimal

from tests.helpers import auth_headers, register


def _seed_operations(client):
    """Ingreso pagado 5000 + gasto pagado 2000 sobre una Caja con 10000 inicial."""
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = client.get("/api/categories?kind=INCOME", headers=headers).json()[0]
    renta = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Renta"
    )
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta grande",
            "amount": "5000",
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
            "amount": "2000",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    return headers, account


def test_profit_loss_matches_ledger(client):
    headers, _ = _seed_operations(client)
    report = client.get(
        "/api/reports/profit-loss?start=2026-08-01&end=2026-08-31", headers=headers
    ).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("5000")
    assert Decimal(str(report["total_expenses"])) == Decimal("2000")
    assert Decimal(str(report["net_profit"])) == Decimal("3000")


def test_balance_sheet_balances(client):
    headers, _ = _seed_operations(client)
    report = client.get("/api/reports/balance-sheet?as_of=2026-12-31", headers=headers).json()
    assert report["balanced"] is True
    total_assets = Decimal(str(report["total_assets"]))
    # Caja: 10000 inicial + 5000 - 2000 = 13000
    assert total_assets == Decimal("13000")
    assert total_assets == Decimal(str(report["total_liabilities"])) + Decimal(str(report["total_equity"]))


def test_cash_flow_closing_matches_account_balance(client):
    headers, account = _seed_operations(client)
    report = client.get(
        "/api/reports/cash-flow?start=2026-08-01&end=2026-08-31", headers=headers
    ).json()
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert Decimal(str(report["closing_cash"])) == Decimal(balance)


def test_trial_balance_endpoint_balanced(client):
    headers, _ = _seed_operations(client)
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(report["total_debit"])) == Decimal(str(report["total_credit"]))


def test_dashboard_summary_shape_and_cash(client):
    headers, _ = _seed_operations(client)
    body = client.get("/api/dashboard/summary", headers=headers).json()
    for key in (
        "cash",
        "monthly_revenue",
        "monthly_expenses",
        "monthly_profit",
        "receivables",
        "payables",
        "cash_flow",
        "revenue_vs_expenses",
        "expense_categories",
    ):
        assert key in body
    assert Decimal(str(body["cash"])) == Decimal("13000")


def test_dashboard_receivables_and_payables(client):
    headers, account = _seed_operations(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente Crédito"}).json()
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Proveedor Crédito"}).json()
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    renta = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Renta"
    )
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Venta a crédito vencida",
            "amount": "7000",
            "due_date": "2026-01-01",
            "category_id": ventas["id"],
        },
    ).json()
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "2000", "financial_account_id": account["id"]},
    )
    client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Compra a crédito",
            "amount": "4000",
            "due_date": "2027-01-31",
            "category_id": renta["id"],
        },
    )

    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(str(summary["receivables"])) == Decimal("5000")
    assert Decimal(str(summary["overdue_receivables"])) == Decimal("5000")
    assert Decimal(str(summary["payables"])) == Decimal("4000")

    # El balance sigue cuadrando con AR en activos y AP en pasivos
    report = client.get("/api/reports/balance-sheet?as_of=2027-12-31", headers=headers).json()
    assert report["balanced"] is True
    assets = {row["code"]: row["amount"] for row in report["assets"]}
    liabilities = {row["code"]: row["amount"] for row in report["liabilities"]}
    assert Decimal(str(assets["1200"])) == Decimal("5000")
    assert Decimal(str(liabilities["2100"])) == Decimal("4000")


def test_accounting_section_forbidden_for_viewer(client, db):
    from app.models.organization import OrganizationMember, ROLE_VIEWER
    from app.models.user import User
    from app.security.passwords import hash_password
    from app.security.tokens import create_access_token

    body = register(client)
    org_id = body["organization"]["id"]
    viewer = User(email="viewer@example.com", password_hash=hash_password("supersegura123"), name="Viewer")
    db.add(viewer)
    db.flush()
    db.add(OrganizationMember(organization_id=org_id, user_id=viewer.id, role=ROLE_VIEWER))
    db.commit()

    response = client.get(
        "/api/accounting/trial-balance",
        headers={
            "Authorization": f"Bearer {create_access_token(viewer.id)}",
            "X-Organization-ID": org_id,
        },
    )
    assert response.status_code == 403
