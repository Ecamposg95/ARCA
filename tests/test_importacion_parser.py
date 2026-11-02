"""Parsers de importación: Toronja (HTML disfrazado de .xls) y archivos tabulares."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.imports.toronja import ToronjaFormatError, parse_toronja
from app.services.imports.values import parse_date, parse_money
from tests.toronja_fixture import UNIT_VILLAS, render_html, sample_tickets, ticket

# --- Valores ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$ 1,240.00", Decimal("1240.00")),
        ("1240", Decimal("1240")),
        ("-350", Decimal("-350")),
        ("$ -", Decimal("0")),
        ("", Decimal("0")),
        ("  (120.50) ", Decimal("-120.50")),
        (1240.5, Decimal("1240.5")),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


def test_parse_money_rejects_text():
    with pytest.raises(ValueError):
        parse_money("mil doscientos")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-15", date(2026, 10, 15)),
        ("15/10/2026", date(2026, 10, 15)),
        ("15-10-2026", date(2026, 10, 15)),
        ("2026-10-15 09:30:00", date(2026, 10, 15)),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_rejects_garbage():
    with pytest.raises(ValueError):
        parse_date("ayer")


# --- Toronja ------------------------------------------------------------------


def test_parses_every_ticket_without_patient_names():
    rows = parse_toronja(render_html(sample_tickets()))
    assert len(rows) == 12
    first = rows[0]
    assert first["folio"] == "1510260001"
    assert first["date"] == date(2026, 10, 15)
    assert first["vendor"] == "MORELOS"
    assert first["cash"] == Decimal("500.00")
    assert first["gran_total"] == Decimal("500.00")
    assert first["row_number"] == 2  # la fila 1 es el encabezado
    for row in rows:
        assert "CLIENTE" not in row and "cliente" not in row
        assert "ESTUDIOS" not in row and "estudios" not in row
        assert "PACIENTE" not in repr(row)


def test_reads_each_payment_column_and_the_broken_discount_header():
    rows = {r["folio"]: r for r in parse_toronja(render_html(sample_tickets()))}
    assert rows["1510260002"]["cash"] == Decimal("740.00")
    assert rows["1510260002"]["discount"] == Decimal("60.00")
    assert rows["1510260002"]["total"] == Decimal("800.00")
    assert rows["1510260003"]["debit_card"] == Decimal("1200.00")
    assert rows["1510260004"]["credit_card"] == Decimal("300.00")
    assert rows["1510260005"]["transfer"] == Decimal("950.00")
    assert rows["1510260007"]["debt"] == Decimal("800.00")
    assert rows["1610260008"]["credit"] == Decimal("1500.00")
    assert rows["1610260009"]["cancelled"] == "SI"
    assert rows["1610260009"]["cancelled_by"] == "ADMIN"
    assert rows["1610260011"]["gran_total"] == Decimal("0.00")


def test_decodes_latin1_vendor_names():
    rows = parse_toronja(render_html(sample_tickets()))
    assert any(r["vendor"] == UNIT_VILLAS for r in rows)


def test_rejects_html_that_is_not_the_toronja_report():
    html = b"<html><body><table><tr><td>Producto</td><td>Precio</td></tr></table></body></html>"
    with pytest.raises(ToronjaFormatError):
        parse_toronja(html)


def test_rejects_non_html_content():
    with pytest.raises(ToronjaFormatError):
        parse_toronja(b"FOLIO,CLIENTE\n1,2\n")


def test_malformed_rows_are_reported_not_dropped():
    bad = ticket("1510260099", "15/10/26", "MORELOS", efectivo="100")
    bad["EFECTIVO"] = "cien pesos"
    rows = parse_toronja(render_html([bad]))
    assert len(rows) == 1
    assert rows[0]["folio"] == "1510260099"
    assert rows[0]["error"]


def test_entities_and_whitespace_in_cells():
    html = render_html(sample_tickets()[:1]).decode("latin-1")
    html = html.replace("<td>MORELOS</td>", "<td>&nbsp; MORELOS &nbsp;</td>").replace(
        "<td>$ 500.00</td>", "<td>\n  $&nbsp;500.00\n</td>"
    )
    rows = parse_toronja(html.encode("latin-1"))
    assert rows[0]["vendor"] == "MORELOS"
    assert rows[0]["cash"] == Decimal("500.00")
