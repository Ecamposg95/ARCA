"""Importación del reporte de ventas de Toronja: vista previa, confirmación, duplicados."""

from decimal import Decimal

from app.models.period import PeriodLock
from tests.helpers import auth_headers, register
from tests.toronja_fixture import UNIT_MORELOS, UNIT_MOVIL, UNIT_VILLAS, render_html, sample_tickets, ticket


def _setup(client, email="dueno@example.com", *, with_settings=True, units=True):
    body = register(client, email=email, initial_cash="1000")
    headers = auth_headers(body)
    ctx = {"headers": headers, "org_id": body["organization"]["id"], "units": {}, "cash": {}}
    if units:
        for name, alias in (("Morelos", UNIT_MORELOS), ("Villas", UNIT_VILLAS), ("Centro Móvil", UNIT_MOVIL)):
            unit = client.post(
                "/api/business-units", headers=headers, json={"name": name, "aliases": [alias]}
            ).json()
            ctx["units"][alias] = unit
            account = client.post(
                "/api/accounts",
                headers=headers,
                json={"name": f"Caja {name}", "type": "CASH", "business_unit_id": unit["id"]},
            )
            assert account.status_code == 201, account.text
            ctx["cash"][alias] = account.json()
    bank = client.post("/api/accounts", headers=headers, json={"name": "BBVA", "type": "BANK"}).json()
    processor = client.post(
        "/api/accounts", headers=headers, json={"name": "Clip (procesador)", "type": "OTHER"}
    ).json()
    ctx["bank"], ctx["processor"] = bank, processor
    if with_settings:
        response = client.patch(
            "/api/organizations/current/import-settings",
            headers=headers,
            json={"toronja": {"bank_account_id": bank["id"], "processor_account_id": processor["id"]}},
        )
        assert response.status_code == 200, response.text
    return ctx


def _upload(client, headers, tickets=None, filename="ventas.xls"):
    content = render_html(tickets if tickets is not None else sample_tickets())
    response = client.post(
        "/api/imports",
        headers=headers,
        files={"file": (filename, content, "application/vnd.ms-excel")},
        data={"kind": "TORONJA"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _rows_by_folio(detail):
    return {row["payload"]["folio"]: row for row in detail["rows"]["items"]}


def _balance(client, headers, account_id) -> Decimal:
    return Decimal(client.get(f"/api/accounts/{account_id}", headers=headers).json()["current_balance"])


# --- Vista previa -------------------------------------------------------------


def test_preview_classifies_every_row(client):
    ctx = _setup(client)
    detail = _upload(client, ctx["headers"])
    assert detail["status"] == "PREVIEW"
    assert detail["kind"] == "TORONJA"
    assert detail["summary"] == {
        "rows": 12,
        "ok": 9,
        "errors": 1,
        "duplicates": 0,
        "skipped": 2,
        "created": 0,
        "operations": 8,
    }
    rows = _rows_by_folio(detail)
    assert rows["1510260001"]["status"] == "OK"
    assert rows["1510260001"]["payload"]["unit_name"] == "Morelos"
    assert rows["1510260001"]["payload"]["cash_account_id"] == ctx["cash"][UNIT_MORELOS]["id"]
    assert rows["1510260003"]["payload"]["processor_account_id"] == ctx["processor"]["id"]
    assert rows["1510260005"]["payload"]["bank_account_id"] == ctx["bank"]["id"]
    assert rows["1610260009"]["status"] == "SKIPPED"
    assert "ancelado" in rows["1610260009"]["message"]
    assert rows["1610260010"]["status"] == "ERROR"
    assert rows["1610260010"]["message"] == (
        "Vendedor sin unidad: SUCURSAL FANTASMA. Agrégalo como alias en Configuración."
    )
    assert rows["1610260011"]["status"] == "SKIPPED"
    assert rows["1610260012"]["status"] == "OK"


def test_preview_never_stores_patient_names_or_studies(client):
    ctx = _setup(client)
    detail = _upload(client, ctx["headers"])
    page = client.get(f"/api/imports/{detail['id']}?limit=1000", headers=ctx["headers"]).json()
    blob = str(page)
    assert "PACIENTE DE PRUEBA" not in blob
    assert "BH, QS" not in blob
    for row in page["rows"]["items"]:
        assert "cliente" not in {k.lower() for k in row["payload"]}
        assert "estudios" not in {k.lower() for k in row["payload"]}


def test_rows_can_be_filtered_by_status(client):
    ctx = _setup(client)
    detail = _upload(client, ctx["headers"])
    page = client.get(f"/api/imports/{detail['id']}?status=ERROR", headers=ctx["headers"]).json()
    assert page["rows"]["total"] == 1
    assert page["rows"]["items"][0]["payload"]["folio"] == "1610260010"
    listing = client.get("/api/imports", headers=ctx["headers"]).json()
    assert listing["total"] == 1
    assert listing["items"][0]["filename"] == "ventas.xls"


def test_missing_processor_only_blocks_card_rows(client):
    ctx = _setup(client, with_settings=False)
    rows = _rows_by_folio(_upload(client, ctx["headers"]))
    assert rows["1510260001"]["status"] == "OK"
    assert rows["1510260003"]["status"] == "ERROR"
    assert "procesador" in rows["1510260003"]["message"]
    assert rows["1510260005"]["status"] == "ERROR"
    assert "banco" in rows["1510260005"]["message"]


def test_unit_without_cash_account_is_an_error(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    unit = client.post("/api/business-units", headers=headers, json={"name": "Sin caja", "aliases": ["SINCAJA"]}).json()
    rows = _rows_by_folio(_upload(client, headers, [ticket("0101260001", "2026-01-01", "sincaja", efectivo="10")]))
    assert rows["0101260001"]["status"] == "ERROR"
    assert rows["0101260001"]["message"] == "La unidad Sin caja no tiene caja."
    assert rows["0101260001"]["payload"]["unit_id"] == unit["id"]


def test_not_a_toronja_file_is_rejected_in_spanish(client):
    ctx = _setup(client)
    response = client.post(
        "/api/imports",
        headers=ctx["headers"],
        files={"file": ("otro.xls", b"<table><tr><td>Hola</td></tr></table>", "text/html")},
        data={"kind": "TORONJA"},
    )
    assert response.status_code == 400
    assert "Toronja" in response.json()["detail"]
    assert client.get("/api/imports", headers=ctx["headers"]).json()["total"] == 0


# --- Confirmar ----------------------------------------------------------------


def test_confirm_creates_grouped_incomes_and_receivables(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    before = {name: _balance(client, headers, acc["id"]) for name, acc in ctx["cash"].items()}
    detail = _upload(client, headers)

    response = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers)
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_at"]
    assert confirmed["summary"]["created"] == 8
    assert confirmed["summary"]["ok"] == 0
    assert confirmed["summary"]["errors"] == 1
    assert confirmed["summary"]["skipped"] == 2

    incomes = client.get("/api/income?limit=100", headers=headers).json()["items"]
    by_desc = {i["description"]: i for i in incomes}
    assert len(incomes) == 6
    morelos_cash = by_desc["Ventas Toronja · Morelos · efectivo · 2 tickets"]
    assert Decimal(morelos_cash["amount"]) == Decimal("1240.00")  # 500 + 740, sin el descuento
    assert morelos_cash["financial_account_id"] == ctx["cash"][UNIT_MORELOS]["id"]
    assert morelos_cash["business_unit_id"] == ctx["units"][UNIT_MORELOS]["id"]
    assert morelos_cash["status"] == "PAID"
    assert morelos_cash["date"] == "2026-10-15"
    assert morelos_cash["paid_at"].startswith("2026-10-15")
    assert Decimal(morelos_cash["tax_amount"]) == 0
    morelos_card = by_desc["Ventas Toronja · Morelos · tarjeta · 2 tickets"]
    assert Decimal(morelos_card["amount"]) == Decimal("1500.00")
    assert morelos_card["financial_account_id"] == ctx["processor"]["id"]
    morelos_transfer = by_desc["Ventas Toronja · Morelos · transferencia · 1 ticket"]
    assert Decimal(morelos_transfer["amount"]) == Decimal("950.00")
    assert morelos_transfer["financial_account_id"] == ctx["bank"]["id"]
    assert Decimal(by_desc["Ventas Toronja · Villas · efectivo · 2 tickets"]["amount"]) == Decimal("600.00")
    assert Decimal(by_desc["Ventas Toronja · Centro Móvil · efectivo · 1 ticket"]["amount"]) == Decimal("150.00")
    assert Decimal(by_desc["Ventas Toronja · Centro Móvil · tarjeta · 1 ticket"]["amount"]) == Decimal("350.00")

    receivables = client.get("/api/receivables?limit=100", headers=headers).json()["items"]
    assert len(receivables) == 2
    by_desc = {r["description"]: r for r in receivables}
    villas_15 = by_desc["Adeudos Toronja · Villas · 2026-10-15 · 1 folio"]
    assert Decimal(villas_15["amount"]) == Decimal("800.00")
    assert villas_15["due_date"] == "2026-11-14"
    assert villas_15["business_unit_id"] == ctx["units"][UNIT_VILLAS]["id"]
    villas_16 = by_desc["Adeudos Toronja · Villas · 2026-10-16 · 1 folio"]
    assert Decimal(villas_16["amount"]) == Decimal("1500.00")
    customers = client.get("/api/customers", headers=headers).json()
    items = customers["items"] if isinstance(customers, dict) else customers
    assert any(c["name"] == "Pacientes (Toronja)" for c in items)
    assert villas_15["customer_id"] == next(c["id"] for c in items if c["name"] == "Pacientes (Toronja)")

    # Los saldos suben lo justo.
    assert _balance(client, headers, ctx["cash"][UNIT_MORELOS]["id"]) - before[UNIT_MORELOS] == Decimal("1240.00")
    assert _balance(client, headers, ctx["cash"][UNIT_VILLAS]["id"]) - before[UNIT_VILLAS] == Decimal("600.00")
    assert _balance(client, headers, ctx["cash"][UNIT_MOVIL]["id"]) - before[UNIT_MOVIL] == Decimal("150.00")
    assert _balance(client, headers, ctx["processor"]["id"]) == Decimal("1850.00")
    assert _balance(client, headers, ctx["bank"]["id"]) == Decimal("950.00")

    # Trazabilidad: cada fila OK quedó CREATED apuntando a lo que creó.
    rows = _rows_by_folio(confirmed)
    assert rows["1510260001"]["status"] == "CREATED"
    assert rows["1510260001"]["result_type"] == "income"
    assert rows["1510260001"]["result_id"] == morelos_cash["id"]
    assert rows["1510260007"]["result_type"] == "income"
    assert {r["type"] for r in rows["1510260007"]["payload"]["results"]} == {"income", "receivable"}
    assert rows["1610260008"]["result_type"] == "receivable"
    assert rows["1610260008"]["result_id"] == villas_16["id"]
    assert rows["1610260010"]["status"] == "ERROR"

    # El movimiento lleva la referencia y la forma de pago de Toronja.
    movements = client.get(
        f"/api/transactions?account_id={ctx['processor']['id']}", headers=headers
    ).json()["items"]
    assert {m["payment_method"] for m in movements} == {"TARJETA"}
    assert any(m["reference"] == "toronja:2026-10-15:MORELOS:tarjeta" for m in movements)


def test_reimporting_the_same_file_creates_nothing(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    first = _upload(client, headers)
    assert client.post(f"/api/imports/{first['id']}/confirm", headers=headers).status_code == 200

    second = _upload(client, headers)
    assert second["summary"]["duplicates"] == 9
    assert second["summary"]["ok"] == 0
    assert second["summary"]["operations"] == 0
    rows = _rows_by_folio(second)
    assert rows["1510260001"]["status"] == "DUPLICATE"
    assert "ya se importó" in rows["1510260001"]["message"]
    # El vendedor desconocido sigue en error: no se importó, así que no es duplicado.
    assert rows["1610260010"]["status"] == "ERROR"

    response = client.post(f"/api/imports/{second['id']}/confirm", headers=headers)
    assert response.status_code == 200
    assert response.json()["summary"]["created"] == 0
    assert client.get("/api/income?limit=100", headers=headers).json()["total"] == 6
    assert client.get("/api/receivables?limit=100", headers=headers).json()["total"] == 2


def test_duplicate_folio_inside_the_file(client):
    ctx = _setup(client)
    tickets = [
        ticket("1510260001", "2026-10-15", UNIT_MORELOS, efectivo="100"),
        ticket("1510260001", "2026-10-15", UNIT_MORELOS, efectivo="100"),
    ]
    rows = _upload(client, ctx["headers"], tickets)["rows"]["items"]
    assert [r["status"] for r in rows] == ["OK", "DUPLICATE"]
    assert rows[0]["payload"]["folio"] == rows[1]["payload"]["folio"]


def test_closed_month_blocks_only_its_rows(client, db):
    ctx = _setup(client)
    db.add(PeriodLock(organization_id=ctx["org_id"], year=2026, month=9))
    db.commit()
    tickets = [
        ticket("3009260001", "2026-09-30", UNIT_MORELOS, efectivo="100"),
        ticket("0110260002", "2026-10-01", UNIT_MORELOS, efectivo="200"),
    ]
    detail = _upload(client, ctx["headers"], tickets)
    rows = _rows_by_folio(detail)
    assert rows["3009260001"]["status"] == "ERROR"
    assert rows["3009260001"]["message"].startswith("Mes cerrado")
    assert rows["0110260002"]["status"] == "OK"
    confirmed = client.post(f"/api/imports/{detail['id']}/confirm", headers=ctx["headers"]).json()
    assert confirmed["summary"]["created"] == 1
    assert _balance(client, ctx["headers"], ctx["cash"][UNIT_MORELOS]["id"]) == Decimal("200.00")


def test_confirm_twice_or_after_discard_is_refused(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    detail = _upload(client, headers)
    assert client.post(f"/api/imports/{detail['id']}/confirm", headers=headers).status_code == 200
    again = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers)
    assert again.status_code == 400
    assert "ya se hizo" in again.json()["detail"]

    other = _upload(client, headers)
    discarded = client.post(f"/api/imports/{other['id']}/discard", headers=headers)
    assert discarded.status_code == 200
    assert discarded.json()["status"] == "DISCARDED"
    refused = client.post(f"/api/imports/{other['id']}/confirm", headers=headers)
    assert refused.status_code == 400
    assert client.get("/api/income?limit=100", headers=headers).json()["total"] == 6


# --- Aislamiento y permisos ---------------------------------------------------


def test_batches_are_tenant_isolated(client):
    mine = _setup(client)
    detail = _upload(client, mine["headers"])
    other = _setup(client, email="otra@example.com")
    assert client.get(f"/api/imports/{detail['id']}", headers=other["headers"]).status_code == 404
    assert client.post(f"/api/imports/{detail['id']}/confirm", headers=other["headers"]).status_code == 404
    assert client.get("/api/imports", headers=other["headers"]).json()["total"] == 0
    # Mismo folio en otra empresa: no es duplicado, cada empresa tiene su Toronja.
    theirs = _upload(client, other["headers"], [ticket("1510260001", "2026-10-15", UNIT_MORELOS, efectivo="5")])
    assert theirs["summary"]["duplicates"] == 0


def test_import_settings_are_validated(client):
    ctx = _setup(client, with_settings=False)
    headers = ctx["headers"]
    assert client.get("/api/organizations/current/import-settings", headers=headers).json() == {
        "toronja": {
            "bank_account_id": None,
            "processor_account_id": None,
            "receivable_customer_id": None,
            "income_category_id": None,
        }
    }
    bad = client.patch(
        "/api/organizations/current/import-settings",
        headers=headers,
        json={"toronja": {"processor_account_id": "no-existe"}},
    )
    assert bad.status_code == 400
    stranger = _setup(client, email="otra@example.com", units=False)
    foreign = client.patch(
        "/api/organizations/current/import-settings",
        headers=headers,
        json={"toronja": {"bank_account_id": stranger["bank"]["id"]}},
    )
    assert foreign.status_code == 400
    ok = client.patch(
        "/api/organizations/current/import-settings",
        headers=headers,
        json={"toronja": {"bank_account_id": ctx["bank"]["id"]}},
    )
    assert ok.status_code == 200
    saved = client.get("/api/organizations/current/import-settings", headers=headers).json()
    assert saved["toronja"]["bank_account_id"] == ctx["bank"]["id"]
    assert saved["toronja"]["processor_account_id"] is None


def test_confirm_is_all_or_nothing(client):
    """Si una operación falla a media importación, no queda ninguna creada."""
    ctx = _setup(client)
    headers = ctx["headers"]
    detail = _upload(client, headers)
    # Entre la vista previa y la confirmación alguien desactivó el procesador.
    deactivated = client.patch(f"/api/accounts/{ctx['processor']['id']}", headers=headers, json={"active": False})
    assert deactivated.status_code == 200, deactivated.text

    response = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"].startswith("No se importó nada")
    assert client.get("/api/income?limit=100", headers=headers).json()["total"] == 0
    assert client.get("/api/receivables?limit=100", headers=headers).json()["total"] == 0
    assert _balance(client, headers, ctx["cash"][UNIT_MORELOS]["id"]) == Decimal("0.00")
    batch = client.get(f"/api/imports/{detail['id']}", headers=headers).json()
    assert batch["status"] == "PREVIEW"
    assert batch["summary"]["created"] == 0
