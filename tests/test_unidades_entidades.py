"""Unidades de negocio y entidad fiscal: dos dimensiones opcionales del libro.

Una empresa sin unidades ni entidades sigue exactamente igual que hoy; con
ellas, cada operación y su póliza las heredan y los reportes se filtran.
"""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com", initial_cash="100000"):
    body = register(client, email=email, initial_cash=initial_cash)
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    nomina = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Nómina"
    )
    return headers, account, ventas, nomina


def _unit(client, headers, name, **extra):
    response = client.post("/api/business-units", headers=headers, json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _entity(client, headers, name, **extra):
    response = client.post("/api/fiscal-entities", headers=headers, json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


# --- Catálogos -----------------------------------------------------------------


def test_business_unit_derives_code_and_lists(client):
    headers, *_ = _setup(client)
    unit = _unit(client, headers, "Morelos", kind="TOMA_MUESTRA", aliases=["MORELOS"])
    assert unit["code"] == "MORELOS"
    assert unit["kind"] == "TOMA_MUESTRA"
    assert unit["active"] is True
    assert unit["accounts_count"] == 0

    page = client.get("/api/business-units", headers=headers).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == unit["id"]


def test_business_unit_name_is_unique_case_insensitive(client):
    headers, *_ = _setup(client)
    _unit(client, headers, "Morelos")
    response = client.post("/api/business-units", headers=headers, json={"name": "  morelos "})
    assert response.status_code == 400
    assert "Morelos" in response.json()["detail"] or "unidad" in response.json()["detail"].lower()


def test_only_one_active_matriz(client):
    headers, *_ = _setup(client)
    _unit(client, headers, "Centro Médico", kind="MATRIZ")
    response = client.post("/api/business-units", headers=headers, json={"name": "Otra", "kind": "MATRIZ"})
    assert response.status_code == 400
    assert "matriz" in response.json()["detail"].lower()


def test_alias_is_normalized_and_unique_within_org(client):
    headers, *_ = _setup(client)
    _unit(client, headers, "Villas", aliases=["VILLAS DE NUESTRA SEÑORA", "VNSA MOVIL"])
    # Mismo alias con acentos, minúsculas y espacios de más: es el mismo.
    response = client.post(
        "/api/business-units",
        headers=headers,
        json={"name": "Unidad Móvil", "aliases": ["vnsa   móvil"]},
    )
    assert response.status_code == 400
    assert "alias" in response.json()["detail"].lower()


def test_business_unit_patch_and_deactivate(client):
    headers, *_ = _setup(client)
    unit = _unit(client, headers, "Cumbres")
    response = client.patch(
        f"/api/business-units/{unit['id']}",
        headers=headers,
        json={"active": False, "opened_on": "2026-01-01", "aliases": ["CUMBRES"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is False
    assert response.json()["opened_on"] == "2026-01-01"

    active_only = client.get("/api/business-units?active=true", headers=headers).json()
    assert active_only["total"] == 0


def test_fiscal_entity_crud(client):
    headers, *_ = _setup(client)
    entity = _entity(client, headers, "Liza", tax_id="dial900101ab1", regime="Persona física con actividad empresarial")
    assert entity["tax_id"] == "DIAL900101AB1"
    page = client.get("/api/fiscal-entities", headers=headers).json()
    assert page["total"] == 1

    response = client.patch(f"/api/fiscal-entities/{entity['id']}", headers=headers, json={"regime": "RESICO"})
    assert response.status_code == 200
    assert response.json()["regime"] == "RESICO"

    response = client.post("/api/fiscal-entities", headers=headers, json={"name": "liza"})
    assert response.status_code == 400


def test_catalogs_are_tenant_isolated(client):
    headers_a, *_ = _setup(client, email="a@example.com")
    headers_b, *_ = _setup(client, email="b@example.com")
    unit_b = _unit(client, headers_b, "Sucursal B")
    entity_b = _entity(client, headers_b, "Contribuyente B")

    assert client.get("/api/business-units", headers=headers_a).json()["total"] == 0
    assert client.get("/api/fiscal-entities", headers=headers_a).json()["total"] == 0
    assert client.patch(f"/api/business-units/{unit_b['id']}", headers=headers_a, json={"name": "x"}).status_code == 404
    assert client.patch(f"/api/fiscal-entities/{entity_b['id']}", headers=headers_a, json={"name": "x"}).status_code == 404


def test_organization_exposes_dimension_flags(client):
    headers, *_ = _setup(client)
    current = client.get("/api/organizations/current", headers=headers).json()
    assert current["has_business_units"] is False
    assert current["has_fiscal_entities"] is False

    _unit(client, headers, "Morelos")
    _entity(client, headers, "Liza")
    current = client.get("/api/organizations/current", headers=headers).json()
    assert current["has_business_units"] is True
    assert current["has_fiscal_entities"] is True


def test_viewer_cannot_write_catalogs(client):
    headers, *_ = _setup(client)
    client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": "viewer@example.com", "name": "Lector", "role": "VIEWER", "password": "supersegura123"},
    )
    login = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "supersegura123"})
    assert login.status_code == 200, login.text
    viewer_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Organization-ID": headers["X-Organization-ID"],
    }
    assert client.get("/api/business-units", headers=viewer_headers).status_code == 200
    assert client.post("/api/business-units", headers=viewer_headers, json={"name": "x"}).status_code == 403


# --- Operaciones, póliza y reverso ----------------------------------------------


def _account(client, headers, name, business_unit_id=None, opening="0"):
    payload = {"name": name, "type": "CASH", "opening_balance": opening}
    if business_unit_id:
        payload["business_unit_id"] = business_unit_id
    response = client.post("/api/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _income(client, headers, account, category, amount, **extra):
    payload = {
        "date": date.today().isoformat(),
        "description": "Venta",
        "amount": amount,
        "category_id": category["id"],
        "financial_account_id": account["id"],
        "status": "PAID",
        **extra,
    }
    response = client.post("/api/income", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _expense(client, headers, account, category, amount, **extra):
    payload = {
        "date": date.today().isoformat(),
        "description": "Gasto",
        "amount": amount,
        "category_id": category["id"],
        "financial_account_id": account["id"],
        "status": "PAID",
        **extra,
    }
    response = client.post("/api/expenses", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _entries(client, headers, source_type, source_id):
    page = client.get(
        f"/api/accounting/journal-entries?source_type={source_type}&source_id={source_id}", headers=headers
    ).json()
    return page["items"]


def test_income_inherits_unit_from_account_and_tags_entry(client):
    headers, _central, ventas, _nomina = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    caja = _account(client, headers, "Caja Morelos", morelos["id"])
    assert caja["business_unit_id"] == morelos["id"]

    income = _income(client, headers, caja, ventas, "1000")
    assert income["business_unit_id"] == morelos["id"]
    assert income["business_unit_name"] == "Morelos"
    assert income["fiscal_entity_id"] is None  # nada se infiere para la entidad

    (entry,) = _entries(client, headers, "income", income["id"])
    assert entry["business_unit_id"] == morelos["id"]
    assert entry["business_unit_name"] == "Morelos"

    movements = client.get(f"/api/transactions?business_unit_id={morelos['id']}", headers=headers).json()
    assert [m["source_id"] for m in movements["items"]] == [income["id"]]
    assert movements["items"][0]["business_unit_name"] == "Morelos"

    unit = client.get("/api/business-units", headers=headers).json()["items"][0]
    assert unit["accounts_count"] == 1


def test_operation_unit_wins_over_account_unit(client):
    headers, central, _ventas, nomina = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    liza = _entity(client, headers, "Liza")

    expense = _expense(
        client, headers, central, nomina, "500", business_unit_id=morelos["id"], fiscal_entity_id=liza["id"]
    )
    assert expense["business_unit_id"] == morelos["id"]
    assert expense["fiscal_entity_name"] == "Liza"

    (entry,) = _entries(client, headers, "expense", expense["id"])
    assert entry["business_unit_id"] == morelos["id"]
    assert entry["fiscal_entity_id"] == liza["id"]

    # El movimiento de dinero lleva la unidad de la cuenta (la central no tiene).
    movement = client.get(f"/api/transactions?source_type=expense&source_id={expense['id']}", headers=headers).json()
    assert movement["items"][0]["business_unit_id"] is None
    # ...pero sí se encuentra por contribuyente, vía su póliza.
    by_entity = client.get(f"/api/transactions?fiscal_entity_id={liza['id']}", headers=headers).json()
    assert [m["source_id"] for m in by_entity["items"]] == [expense["id"]]


def test_reversal_copies_dimensions(client):
    headers, central, ventas, _nomina = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    ale = _entity(client, headers, "Ale", regime="RESICO")
    income = _income(
        client, headers, central, ventas, "800", business_unit_id=morelos["id"], fiscal_entity_id=ale["id"]
    )

    response = client.post(f"/api/income/{income['id']}/cancel", headers=headers, json={"reason": "error"})
    assert response.status_code == 200, response.text

    entries = _entries(client, headers, "income", income["id"])
    assert len(entries) == 2
    reversal = next(e for e in entries if e["reversal_of"])
    assert reversal["business_unit_id"] == morelos["id"]
    assert reversal["fiscal_entity_id"] == ale["id"]

    movements = client.get(f"/api/transactions?fiscal_entity_id={ale['id']}", headers=headers).json()
    assert {m["transaction_type"] for m in movements["items"]} == {"INCOME", "REVERSAL_OUT"}


def test_foreign_or_inactive_dimension_is_rejected(client):
    headers_a, central_a, ventas_a, _ = _setup(client, email="a@example.com")
    headers_b, *_ = _setup(client, email="b@example.com")
    unit_b = _unit(client, headers_b, "Ajena")
    entity_b = _entity(client, headers_b, "Ajeno")

    payload = {
        "date": date.today().isoformat(),
        "description": "cruce",
        "amount": "100",
        "category_id": ventas_a["id"],
        "financial_account_id": central_a["id"],
    }
    foreign_unit = client.post("/api/income", headers=headers_a, json={**payload, "business_unit_id": unit_b["id"]})
    assert foreign_unit.status_code == 404
    foreign_entity = client.post("/api/income", headers=headers_a, json={**payload, "fiscal_entity_id": entity_b["id"]})
    assert foreign_entity.status_code == 404
    foreign_account = client.post(
        "/api/accounts", headers=headers_a, json={"name": "x", "type": "CASH", "business_unit_id": unit_b["id"]}
    )
    assert foreign_account.status_code == 404

    cumbres = _unit(client, headers_a, "Cumbres")
    client.patch(f"/api/business-units/{cumbres['id']}", headers=headers_a, json={"active": False})
    response = client.post("/api/income", headers=headers_a, json={**payload, "business_unit_id": cumbres["id"]})
    assert response.status_code == 400
    assert "inactiva" in response.json()["detail"]


def test_cannot_deactivate_unit_whose_cash_has_balance(client):
    headers, *_ = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    _account(client, headers, "Caja Morelos", morelos["id"], opening="250")
    response = client.patch(f"/api/business-units/{morelos['id']}", headers=headers, json={"active": False})
    assert response.status_code == 400
    assert response.json()["detail"] == "Primero traspasa el saldo de sus cajas."


def test_transfer_legs_carry_their_account_unit(client):
    headers, central, *_ = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    caja = _account(client, headers, "Caja Morelos", morelos["id"])
    response = client.post(
        "/api/transactions/transfer",
        headers=headers,
        json={
            "from_account_id": central["id"],
            "to_account_id": caja["id"],
            "amount": "300",
            "date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    outgoing, incoming = response.json()
    assert outgoing["business_unit_id"] is None
    assert incoming["business_unit_id"] == morelos["id"]


def test_receivable_and_payable_carry_dimensions(client):
    headers, central, ventas, nomina = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    liza = _entity(client, headers, "Liza")
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Proveedor"}).json()

    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura",
            "amount": "1000",
            "due_date": date.today().isoformat(),
            "category_id": ventas["id"],
            "business_unit_id": morelos["id"],
            "fiscal_entity_id": liza["id"],
        },
    ).json()
    assert receivable["business_unit_name"] == "Morelos"
    collected = client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "1000", "financial_account_id": central["id"]},
    )
    assert collected.status_code in (200, 201), collected.text
    entries = _entries(client, headers, "receivable", receivable["id"])
    assert len(entries) == 2
    for entry in entries:
        assert entry["business_unit_id"] == morelos["id"]
        assert entry["fiscal_entity_id"] == liza["id"]

    payable = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Compra",
            "amount": "400",
            "due_date": date.today().isoformat(),
            "category_id": nomina["id"],
            "fiscal_entity_id": liza["id"],
        },
    ).json()
    assert payable["fiscal_entity_name"] == "Liza"
    assert client.get(f"/api/payables?fiscal_entity_id={liza['id']}", headers=headers).json()["total"] == 1
    assert client.get(f"/api/receivables?business_unit_id={morelos['id']}", headers=headers).json()["total"] == 1


# --- Reportes y tablero ----------------------------------------------------------


def test_reports_filter_sums_exactly_that_unit(client):
    headers, central, ventas, nomina = _setup(client)
    morelos = _unit(client, headers, "Morelos")
    alameda = _unit(client, headers, "Alameda")
    liza = _entity(client, headers, "Liza")
    caja_morelos = _account(client, headers, "Caja Morelos", morelos["id"])
    caja_alameda = _account(client, headers, "Caja Alameda", alameda["id"])

    _income(client, headers, caja_morelos, ventas, "1000", fiscal_entity_id=liza["id"])
    _income(client, headers, caja_alameda, ventas, "500")
    _expense(client, headers, caja_morelos, nomina, "200")
    _expense(client, headers, central, nomina, "50")

    full = client.get("/api/reports/profit-loss", headers=headers).json()
    assert Decimal(str(full["total_revenue"])) == Decimal("1500")
    assert Decimal(str(full["total_expenses"])) == Decimal("250")

    by_unit = client.get(f"/api/reports/profit-loss?business_unit_id={morelos['id']}", headers=headers).json()
    assert Decimal(str(by_unit["total_revenue"])) == Decimal("1000")
    assert Decimal(str(by_unit["total_expenses"])) == Decimal("200")

    by_entity = client.get(f"/api/reports/profit-loss?fiscal_entity_id={liza['id']}", headers=headers).json()
    assert Decimal(str(by_entity["total_revenue"])) == Decimal("1000")
    assert Decimal(str(by_entity["total_expenses"])) == Decimal("0")

    balanza = client.get(f"/api/accounting/trial-balance?business_unit_id={morelos['id']}", headers=headers).json()
    assert balanza["total_debit"] == balanza["total_credit"]
    revenue_row = next(r for r in balanza["rows"] if r["type"] == "REVENUE")
    assert Decimal(str(revenue_row["balance"])) == Decimal("1000")

    diario = client.get(f"/api/accounting/journal-entries?business_unit_id={morelos['id']}", headers=headers).json()
    assert diario["total"] == 2

    flow = client.get(f"/api/reports/cash-flow?business_unit_id={morelos['id']}", headers=headers).json()
    assert Decimal(str(flow["inflows"])) == Decimal("1000")
    assert Decimal(str(flow["outflows"])) == Decimal("200")

    summary = client.get(f"/api/dashboard/summary?business_unit_id={morelos['id']}", headers=headers).json()
    assert Decimal(str(summary["cash"])) == Decimal("800")
    assert Decimal(str(summary["monthly_revenue"])) == Decimal("1000")
    assert Decimal(str(summary["monthly_expenses"])) == Decimal("200")
    assert Decimal(str(summary["expense_categories"][0]["amount"])) == Decimal("200")

    series = client.get(f"/api/reports/cash-series?business_unit_id={morelos['id']}", headers=headers).json()
    assert [a["name"] for a in series["accounts"]] == ["Caja Morelos"]

    balance = client.get(f"/api/reports/balance-sheet?business_unit_id={morelos['id']}", headers=headers).json()
    assert Decimal(str(balance["total_assets"])) == Decimal("800")


def test_org_without_units_reads_null_dimensions(client):
    headers, central, ventas, _ = _setup(client)
    income = _income(client, headers, central, ventas, "100")
    assert income["business_unit_id"] is None and income["business_unit_name"] is None
    assert income["fiscal_entity_id"] is None and income["fiscal_entity_name"] is None
    page = client.get("/api/income", headers=headers).json()
    assert page["total"] == 1
