"""Lector del reporte de ventas de Toronja.

Toronja exporta un `.xls` que en realidad es HTML: una `<table>` con una fila
de encabezado y una por ticket, en latin-1. Aquí sólo se lee: texto → lista de
diccionarios con Decimal y fechas. Los nombres de pacientes (`CLIENTE`) y los
estudios NUNCA salen de esta función: el diccionario no los incluye.
"""

from __future__ import annotations

from html.parser import HTMLParser

from app.services.dimensions import normalize_alias
from app.services.imports.values import clean_text, parse_date, parse_money


class ToronjaFormatError(ValueError):
    """El archivo no es el reporte de ventas de Toronja."""


# Encabezado normalizado → clave del diccionario. Lo que no está aquí se ignora
# (CLIENTE, ESTUDIOS, SUMA ABONO, IVA, TOTAL CON IVA no se usan ni se guardan;
# los dos primeros por privacidad).
MONEY_COLUMNS = {
    "TOTAL": "total",
    "EFECTIVO": "cash",
    "TARJETA DEBITO": "debit_card",
    "TARJETA CREDITO": "credit_card",
    "TRANSFERENCIA": "transfer",
    "CREDITO": "credit",
    # El encabezado viene roto en el archivo real; ambas formas son el descuento.
    "PAGO CON IVA / DESCUENTO": "discount",
    "DESCUENTO": "discount",
    "GRAN TOTAL": "gran_total",
    "ADEUDO": "debt",
}
TEXT_COLUMNS = {
    "FOLIO": "folio",
    "VENDEDOR": "vendor",
    "CANCELADO": "cancelled",
    "CANCELADO POR": "cancelled_by",
    "EDITADO": "edited",
    "FECHA": "date",
}
REQUIRED = ("FOLIO", "GRAN TOTAL", "VENDEDOR", "FECHA", "EFECTIVO")


class _TableRows(HTMLParser):
    """Acumula el texto de cada `<td>`/`<th>` y cierra la fila en `</tr>`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.saw_table = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.saw_table = True
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            if self._row is None:
                self._row = []
            self._row.append(clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def decode(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def parse_toronja(content: bytes) -> list[dict]:
    """Bytes del `.xls` de Toronja → una fila por ticket.

    Cada fila trae `row_number` (1 = encabezado). Una fila que no se pudo leer
    (fecha o monto ilegible) se devuelve con `error` para mostrarla, no se tira.
    """
    parser = _TableRows()
    parser.feed(decode(content))
    parser.close()
    if not parser.saw_table or not parser.rows:
        raise ToronjaFormatError("El archivo no parece el reporte de ventas de Toronja: no tiene tabla.")

    header_index = next(
        (i for i, row in enumerate(parser.rows) if row and normalize_alias(row[0]) == "FOLIO"), None
    )
    if header_index is None:
        raise ToronjaFormatError("El archivo no parece el reporte de ventas de Toronja: falta la columna FOLIO.")
    header = [normalize_alias(cell) for cell in parser.rows[header_index]]
    positions = {name: i for i, name in enumerate(header)}
    missing = [name for name in REQUIRED if name not in positions]
    if missing:
        raise ToronjaFormatError(
            "El archivo no parece el reporte de ventas de Toronja: faltan las columnas " + ", ".join(missing) + "."
        )

    rows: list[dict] = []
    for offset, cells in enumerate(parser.rows[header_index + 1 :], start=header_index + 2):
        if not any(cells):
            continue
        rows.append(_read_row(cells, positions, offset))
    return rows


def _read_row(cells: list[str], positions: dict[str, int], row_number: int) -> dict:
    def cell(name: str) -> str:
        index = positions.get(name)
        return cells[index] if index is not None and index < len(cells) else ""

    row: dict = {"row_number": row_number, "error": None}
    for name, key in TEXT_COLUMNS.items():
        row[key] = cell(name)
    try:
        row["date"] = parse_date(row["date"])
    except ValueError as exc:
        row["date"] = None
        row["error"] = str(exc)
    for name, key in MONEY_COLUMNS.items():
        if key in row and name not in positions:
            continue
        try:
            row[key] = parse_money(cell(name))
        except ValueError as exc:
            row[key] = None
            row["error"] = row["error"] or f"{name}: {exc}"
    for key in set(MONEY_COLUMNS.values()):
        row.setdefault(key, None)
    return row
