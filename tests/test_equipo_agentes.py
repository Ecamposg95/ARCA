"""El equipo de agentes residentes: cinco preguntas con números verificables."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com", cash="300000"):
    body = register(client, email=email, initial_cash=cash)
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    cats = {c["name"]: c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()}
    return headers, account, ventas, cats


def _expense(client, headers, account, categoria, amount, when):
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Gasto",
            "amount": amount,
            "category_id": categoria["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def test_roster_has_the_five_agents(client):
    headers, *_ = _setup(client)
    roster = client.get("/api/agent-team", headers=headers).json()
    assert [a["id"] for a in roster["items"]] == [
        "cfo",
        "treasury",
        "collections",
        "accounting",
        "forecast",
    ]
    cfo = roster["items"][0]
    assert cfo["question"] == "¿Cuándo entramos en zona crítica?"


def test_cfo_scenarios_shrink_with_lower_income(client):
    headers, account, ventas, cats = _setup(client, cash="300000")
    today = date.today()
    # 90 días con ingresos 60k/mes y gastos 90k/mes: quema 30k/mes.
    for months_ago in (0, 1, 2):
        when = today - timedelta(days=30 * months_ago + 5)
        client.post(
            "/api/income",
            headers=headers,
            json={
                "date": when.isoformat(),
                "description": "Venta",
                "amount": "60000",
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )
        _expense(client, headers, account, cats["Renta"], "90000", when + timedelta(days=1))

    brief = client.get("/api/agent-team/cfo/brief", headers=headers).json()
    base, conservador, estres = brief["scenarios"]

    assert Decimal(str(base["runway_months"])) > Decimal(str(conservador["runway_months"]))
    assert Decimal(str(conservador["runway_months"])) > Decimal(str(estres["runway_months"]))
    # La zona crítica existe y tiene fecha cuando el negocio quema caja.
    assert any("Zona crítica" in m["label"] for m in brief["metrics"])


def test_cfo_with_positive_flow_has_no_critical_zone(client):
    headers, account, ventas, _cats = _setup(client)
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta",
            "amount": "100000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    brief = client.get("/api/agent-team/cfo/brief", headers=headers).json()
    assert "Sin zona crítica" in brief["headline"]
    assert brief["scenarios"][0]["runway_months"] is None


def test_treasury_puts_payroll_and_taxes_before_vendors(client):
    headers, account, _ventas, cats = _setup(client)
    today = date.today()
    # Nómina recurrente + un proveedor por vencer.
    client.post(
        "/api/recurring",
        headers=headers,
        json={
            "kind": "EXPENSE",
            "description": "Nómina quincenal",
            "amount": "48000",
            "tax_rate": "0",
            "category_id": cats["Nómina"]["id"],
            "financial_account_id": account["id"],
            "day_of_month": 15,
        },
    )
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Proveedor"}).json()
    client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Factura del proveedor",
            "amount": "10000",
            "due_date": (today + timedelta(days=10)).isoformat(),
            "category_id": cats["Renta"]["id"],
        },
    )

    brief = client.get("/api/agent-team/treasury/brief", headers=headers).json()
    metrics = {m["label"]: m["value"] for m in brief["metrics"]}
    assert metrics["Nómina"] == "$48,000"
    assert metrics["Proveedores"] == "$10,000"
    # El orden del brief: nómina primero, proveedores al final.
    nomina_idx = next(i for i, f in enumerate(brief["findings"]) if "Nómina" in f)
    ap_idx = next(i for i, f in enumerate(brief["findings"]) if "Proveedores" in f)
    assert nomina_idx < ap_idx


def test_collections_measures_concentration(client):
    headers, _account, ventas, _cats = _setup(client)
    today = date.today()
    grande = client.post("/api/customers", headers=headers, json={"name": "Cliente Grande"}).json()
    chico = client.post("/api/customers", headers=headers, json={"name": "Cliente Chico"}).json()
    for customer, amount, overdue in ((grande, "80000", 40), (chico, "20000", 0)):
        client.post(
            "/api/receivables",
            headers=headers,
            json={
                "customer_id": customer["id"],
                "description": f"Factura {customer['name']}",
                "amount": amount,
                "due_date": (today - timedelta(days=overdue)).isoformat()
                if overdue
                else (today + timedelta(days=20)).isoformat(),
                "category_id": ventas["id"],
            },
        )

    brief = client.get("/api/agent-team/collections/brief", headers=headers).json()
    metrics = {m["label"]: m["value"] for m in brief["metrics"]}
    # 80,000 de 100,000 = 80% en un solo cliente.
    assert metrics["Concentración"] == "80.0%"
    assert any("Cliente Grande" in f and "40 días" in f for f in brief["findings"])
    assert any("un solo cliente" in f for f in brief["findings"])


def test_accounting_reports_category_movements(client):
    headers, account, ventas, cats = _setup(client)
    today = date.today()
    prev_month_same_day = (today.replace(day=1) - timedelta(days=1)).replace(
        day=min(today.day, 28)
    )
    # Mes pasado: renta 10,000. Este mes: renta 25,000 → subió 15,000.
    _expense(client, headers, account, cats["Renta"], "10000", prev_month_same_day.replace(day=5))
    _expense(client, headers, account, cats["Renta"], "25000", today.replace(day=min(today.day, 28)))
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": today.isoformat(),
            "description": "Venta",
            "amount": "50000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )

    brief = client.get("/api/agent-team/accounting/brief", headers=headers).json()
    assert any("Renta" in f and "subió" in f and "$15,000" in f for f in brief["findings"])
    assert any(m["label"] == "Margen" for m in brief["metrics"])


def test_forecast_hiring_lowers_runway(client):
    headers, account, ventas, cats = _setup(client, cash="400000")
    today = date.today()
    for months_ago in (0, 1, 2):
        when = today - timedelta(days=30 * months_ago + 5)
        client.post(
            "/api/income",
            headers=headers,
            json={
                "date": when.isoformat(),
                "description": "Venta",
                "amount": "80000",
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )
        _expense(client, headers, account, cats["Renta"], "100000", when + timedelta(days=1))

    brief = client.get(
        "/api/agent-team/forecast/brief?monthly_cost=35000", headers=headers
    ).json()
    base, conservador, growth = brief["scenarios"]
    # Quema 20k/mes; contratar (+35k) la sube a 55k: el runway se encoge.
    assert Decimal(str(base["runway_months"])) > Decimal(str(conservador["runway_months"]))
    assert conservador["hires"] == 1
    assert growth["hires"] == 2


def test_unknown_agent_is_404(client):
    headers, *_ = _setup(client)
    assert client.get("/api/agent-team/inventado/brief", headers=headers).status_code == 404


def test_briefs_are_isolated_by_organization(client):
    headers_a, _account, ventas_a, _cats = _setup(client)
    grande = client.post("/api/customers", headers=headers_a, json={"name": "Sólo De A"}).json()
    client.post(
        "/api/receivables",
        headers=headers_a,
        json={
            "customer_id": grande["id"],
            "description": "Factura de A",
            "amount": "70000",
            "due_date": (date.today() + timedelta(days=10)).isoformat(),
            "category_id": ventas_a["id"],
        },
    )
    headers_b, *_ = _setup(client, email="otra@example.com")
    brief_b = client.get("/api/agent-team/collections/brief", headers=headers_b).json()
    assert not any("Sólo De A" in f for f in brief_b["findings"])
