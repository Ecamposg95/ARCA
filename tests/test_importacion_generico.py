"""Importación genérica: CSV y XLSX con mapeo de columnas para ingresos, gastos y efectivo."""

import io
from decimal import Decimal

import pytest

from app.models.period import PeriodLock
from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="5000")
    headers = auth_headers(body)
    caja = client.get("/api/accounts", headers=headers).json()[0]
    income_cats = client.get("/api/categories?kind=INCOME", headers=headers).json()
    expense_cats = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    ventas = next(c for c in income_cats if c["name"] == "Ventas")
    nomina = next(c for c in expense_cats if c["name"] == "Nómina")
    return {"headers": headers, "org_id": body["organization"]["id"], "caja": caja, "ventas": ventas, "nomina": nomina}


def _upload(client, headers, kind, filename, content, sheet=None):
    data = {"kind": kind}
    if sheet:
        data["sheet"] = sheet
    response = client.post(
        "/api/imports", headers=headers, files={"file": (filename, content, "application/octet-stream")}, data=data
    )
    assert response.status_code == 201, response.text
    return response.json()


def _map(client, headers, batch_id, mapping, defaults=None, expect=200):
    response = client.post(
        f"/api/imports/{batch_id}/map", headers=headers, json={"mapping": mapping, "defaults": defaults or {}}
    )
    assert response.status_code == expect, response.text
    return response.json()


def _balance(client, headers, account_id) -> Decimal:
    return Decimal(client.get(f"/api/accounts/{account_id}", headers=headers).json()["current_balance"])


EXPENSES_CSV = (
    "Fecha,Concepto,Monto,Categoría,Cuenta,Referencia\n"
    "2026-10-03,Sueldo Juan,\"$ 1,200.00\",Nómina,Caja,NOM-1\n"
    "03/10/2026,Sueldo María,800,nomina,Caja,NOM-2\n"
    "2026-10-04,Lunch,150,Comidas y viáticos de otro planeta,Caja,\n"
    "2026-10-03,Sueldo Juan,1200,Nómina,Caja,NOM-1\n"
).encode("utf-8")


# --- Subida y mapeo -----------------------------------------------------------


def test_upload_detects_columns_and_waits_for_mapping(client):
    ctx = _setup(client)
    detail = _upload(client, ctx["headers"], "EXPENSES", "gastos.csv", EXPENSES_CSV)
    assert detail["options"]["columns"] == ["Fecha", "Concepto", "Monto", "Categoría", "Cuenta", "Referencia"]
    assert detail["summary"]["rows"] == 4
    assert detail["summary"]["skipped"] == 4
    assert detail["summary"]["ok"] == 0
    assert detail["rows"]["items"][0]["payload"]["raw"]["Concepto"] == "Sueldo Juan"
    assert detail["rows"]["items"][0]["row_number"] == 2


def test_mapping_classifies_rows_duplicates_and_missing_category(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    detail = _upload(client, headers, "EXPENSES", "gastos.csv", EXPENSES_CSV)
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Fecha", "concepto": "Concepto", "monto": "Monto", "categoria": "Categoría", "cuenta": "Cuenta", "referencia": "Referencia"},
    )
    rows = mapped["rows"]["items"]
    assert [r["status"] for r in rows] == ["OK", "OK", "ERROR", "DUPLICATE"]
    assert rows[0]["payload"]["amount"] == "1200.00"
    assert rows[0]["payload"]["category_id"] == ctx["nomina"]["id"]
    assert rows[0]["payload"]["financial_account_id"] == ctx["caja"]["id"]
    assert rows[0]["payload"]["reference"] == "NOM-1"
    assert rows[1]["payload"]["date"] == "2026-10-03"  # DD/MM/AAAA
    assert rows[1]["payload"]["category_id"] == ctx["nomina"]["id"]  # "nomina" sin acento
    assert rows[2]["message"] == "La categoría Comidas y viáticos de otro planeta no existe."
    assert rows[3]["message"] == "Repetido en el archivo."
    assert rows[3]["external_id"] == rows[0]["external_id"]
    assert mapped["summary"] == {
        "rows": 4,
        "ok": 2,
        "errors": 1,
        "duplicates": 1,
        "skipped": 0,
        "created": 0,
        "operations": 2,
        "from": "2026-10-03",
        "to": "2026-10-03",
    }
    assert mapped["mapping"]["fecha"] == "Fecha"


def test_mapping_requires_date_concept_and_amount(client):
    ctx = _setup(client)
    detail = _upload(client, ctx["headers"], "EXPENSES", "gastos.csv", EXPENSES_CSV)
    error = _map(client, ctx["headers"], detail["id"], {"fecha": "Fecha"}, expect=400)
    assert "concepto" in error["detail"]
    error = _map(client, ctx["headers"], detail["id"], {"fecha": "Fecha", "concepto": "Concepto"}, expect=400)
    assert "monto" in error["detail"]
    error = _map(client, ctx["headers"], detail["id"], {"fecha": "Nada", "concepto": "Concepto", "monto": "Monto"}, expect=400)
    assert "Nada" in error["detail"]


def test_defaults_fill_category_and_account_for_the_whole_batch(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    csv = "Fecha;Concepto;Importe\n2026-10-05;Venta mostrador;$ 2,500.00\n2026-10-06;Venta en línea;1.000,00\n".encode("latin-1")
    detail = _upload(client, headers, "INCOMES", "ingresos.csv", csv)
    assert detail["options"]["columns"] == ["Fecha", "Concepto", "Importe"]
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Fecha", "concepto": "Concepto", "monto": "Importe"},
        {"category_id": ctx["ventas"]["id"], "financial_account_id": ctx["caja"]["id"]},
    )
    rows = mapped["rows"]["items"]
    assert [r["status"] for r in rows] == ["OK", "OK"]
    assert rows[0]["payload"]["amount"] == "2500.00"
    assert rows[0]["payload"]["category_id"] == ctx["ventas"]["id"]
    without_defaults = _map(client, headers, detail["id"], {"fecha": "Fecha", "concepto": "Concepto", "monto": "Importe"})
    assert without_defaults["rows"]["items"][0]["status"] == "ERROR"
    assert "categoría" in without_defaults["rows"]["items"][0]["message"]


# --- Confirmar ----------------------------------------------------------------


def test_confirm_creates_paid_expenses_and_detects_duplicates_on_reimport(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    mapping = {"fecha": "Fecha", "concepto": "Concepto", "monto": "Monto", "categoria": "Categoría", "cuenta": "Cuenta", "referencia": "Referencia"}
    detail = _upload(client, headers, "EXPENSES", "gastos.csv", EXPENSES_CSV)
    _map(client, headers, detail["id"], mapping)
    confirmed = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["summary"]["created"] == 2
    rows = confirmed.json()["rows"]["items"]
    assert rows[0]["status"] == "CREATED" and rows[0]["result_type"] == "expense"

    expenses = client.get("/api/expenses?limit=50", headers=headers).json()["items"]
    assert len(expenses) == 2
    juan = next(e for e in expenses if e["description"] == "Sueldo Juan")
    assert juan["status"] == "PAID"
    assert juan["date"] == "2026-10-03"
    assert Decimal(juan["amount"]) == Decimal("1200.00")
    assert juan["reference"] == "NOM-1"
    assert juan["id"] == rows[0]["result_id"]
    assert _balance(client, headers, ctx["caja"]["id"]) == Decimal("3000.00")

    again = _upload(client, headers, "EXPENSES", "gastos.csv", EXPENSES_CSV)
    mapped = _map(client, headers, again["id"], mapping)
    assert [r["status"] for r in mapped["rows"]["items"]] == ["DUPLICATE", "DUPLICATE", "ERROR", "DUPLICATE"]
    assert "ya se importó" in mapped["rows"]["items"][0]["message"]


def test_cash_file_with_inflow_and_outflow_columns(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    csv = (
        "Día,Descripción,Entrada,Salida\n"
        "2026-10-10,Venta del día,900,\n"
        "2026-10-10,Compra de hielo,,120\n"
        "2026-10-11,Error de captura,50,50\n"
    ).encode("utf-8")
    detail = _upload(client, headers, "CASH", "caja.csv", csv)
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Día", "concepto": "Descripción", "ingreso": "Entrada", "egreso": "Salida"},
        {
            "income_category_id": ctx["ventas"]["id"],
            "expense_category_id": ctx["nomina"]["id"],
            "financial_account_id": ctx["caja"]["id"],
        },
    )
    rows = mapped["rows"]["items"]
    assert [r["status"] for r in rows] == ["OK", "OK", "ERROR"]
    assert rows[0]["payload"]["direction"] == "INCOME"
    assert rows[1]["payload"]["direction"] == "EXPENSE"
    assert "a la vez" in rows[2]["message"]
    confirmed = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers).json()
    assert confirmed["summary"]["created"] == 2
    assert _balance(client, headers, ctx["caja"]["id"]) == Decimal("5780.00")
    assert client.get("/api/income", headers=headers).json()["total"] == 1
    assert client.get("/api/expenses", headers=headers).json()["total"] == 1


def test_cash_file_with_a_single_signed_column(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    csv = "Fecha,Concepto,Monto\n2026-10-10,Venta,300\n2026-10-10,Propina al repartidor,-40\n".encode("utf-8")
    detail = _upload(client, headers, "CASH", "caja.csv", csv)
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Fecha", "concepto": "Concepto", "monto": "Monto"},
        {
            "income_category_id": ctx["ventas"]["id"],
            "expense_category_id": ctx["nomina"]["id"],
            "financial_account_id": ctx["caja"]["id"],
        },
    )
    assert [r["payload"]["direction"] for r in mapped["rows"]["items"]] == ["INCOME", "EXPENSE"]
    assert mapped["rows"]["items"][1]["payload"]["amount"] == "40.00"


def test_closed_month_blocks_only_its_rows(client, db):
    ctx = _setup(client)
    headers = ctx["headers"]
    db.add(PeriodLock(organization_id=ctx["org_id"], year=2026, month=9))
    db.commit()
    csv = "Fecha,Concepto,Monto\n2026-09-30,Renta septiembre,100\n2026-10-01,Renta octubre,200\n".encode("utf-8")
    detail = _upload(client, headers, "EXPENSES", "rentas.csv", csv)
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Fecha", "concepto": "Concepto", "monto": "Monto"},
        {"category_id": ctx["nomina"]["id"], "financial_account_id": ctx["caja"]["id"]},
    )
    rows = mapped["rows"]["items"]
    assert rows[0]["status"] == "ERROR" and rows[0]["message"].startswith("Mes cerrado")
    assert rows[1]["status"] == "OK"
    confirmed = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers).json()
    assert confirmed["summary"]["created"] == 1
    assert _balance(client, headers, ctx["caja"]["id"]) == Decimal("4800.00")


def test_unit_column_resolves_by_alias_and_unknown_unit_is_an_error(client):
    ctx = _setup(client)
    headers = ctx["headers"]
    unit = client.post("/api/business-units", headers=headers, json={"name": "Morelos", "aliases": ["MOR"]}).json()
    csv = "Fecha,Concepto,Monto,Unidad\n2026-10-10,Papelería,80,mor\n2026-10-10,Papelería sur,90,Sur\n".encode("utf-8")
    detail = _upload(client, headers, "EXPENSES", "gastos.csv", csv)
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Fecha", "concepto": "Concepto", "monto": "Monto", "unidad": "Unidad"},
        {"category_id": ctx["nomina"]["id"], "financial_account_id": ctx["caja"]["id"]},
    )
    rows = mapped["rows"]["items"]
    assert rows[0]["status"] == "OK" and rows[0]["payload"]["business_unit_id"] == unit["id"]
    assert rows[1]["status"] == "ERROR" and "Sur" in rows[1]["message"]
    confirmed = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers).json()
    assert confirmed["summary"]["created"] == 1
    expense = client.get("/api/expenses", headers=headers).json()["items"][0]
    assert expense["business_unit_id"] == unit["id"]


# --- XLSX ---------------------------------------------------------------------


def _xlsx(rows: list[list], sheet_title="Hoja1") -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_xlsx_is_read_with_real_dates_and_numbers(client):
    from datetime import datetime

    ctx = _setup(client)
    headers = ctx["headers"]
    content = _xlsx(
        [
            ["Fecha", "Concepto", "Monto"],
            [datetime(2026, 10, 7), "Venta de mostrador", 1500.5],
            [datetime(2026, 10, 8), "Venta en línea", "$ 2,000.00"],
            [None, None, None],
        ],
        sheet_title="Ventas",
    )
    detail = _upload(client, headers, "INCOMES", "ventas.xlsx", content)
    assert detail["options"]["sheets"] == ["Ventas"]
    assert detail["options"]["sheet"] == "Ventas"
    assert detail["summary"]["rows"] == 2
    mapped = _map(
        client,
        headers,
        detail["id"],
        {"fecha": "Fecha", "concepto": "Concepto", "monto": "Monto"},
        {"category_id": ctx["ventas"]["id"], "financial_account_id": ctx["caja"]["id"]},
    )
    rows = mapped["rows"]["items"]
    assert [r["status"] for r in rows] == ["OK", "OK"]
    assert rows[0]["payload"]["date"] == "2026-10-07"
    assert rows[0]["payload"]["amount"] == "1500.50"
    assert rows[1]["payload"]["amount"] == "2000.00"
    confirmed = client.post(f"/api/imports/{detail['id']}/confirm", headers=headers).json()
    assert confirmed["summary"]["created"] == 2
    assert _balance(client, headers, ctx["caja"]["id"]) == Decimal("8500.50")


def test_xlsx_missing_sheet_is_a_clear_error(client):
    ctx = _setup(client)
    content = _xlsx([["Fecha", "Concepto", "Monto"]])
    response = client.post(
        "/api/imports",
        headers=ctx["headers"],
        files={"file": ("x.xlsx", content, "application/octet-stream")},
        data={"kind": "INCOMES", "sheet": "Otra"},
    )
    assert response.status_code == 400
    assert "Otra" in response.json()["detail"]


def test_legacy_xls_is_rejected_for_generic_kinds(client):
    ctx = _setup(client)
    response = client.post(
        "/api/imports",
        headers=ctx["headers"],
        files={"file": ("viejo.xls", b"\xd0\xcf\x11\xe0 binario", "application/vnd.ms-excel")},
        data={"kind": "EXPENSES"},
    )
    assert response.status_code == 400
    assert ".xlsx" in response.json()["detail"]
