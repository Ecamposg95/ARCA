"""CONTROL GENERAL.xlsx → ventas mensuales (PROY), metas 2027, saldos de caja
y bancos a fin de mes (RESUTADOS), préstamos (PRESTAMOS) e inversión por
sucursal (INVERSIONES).

Las cifras de PROY de un mes sin «NO. PACIENTES» son proyección y se
descartan: sólo entra lo que ya ocurrió.
"""

from __future__ import annotations

from datetime import date

from app.domains.analytics.loaders.xlsx import (
    cell,
    month_of,
    money,
    norm,
    open_workbook,
    sheet_rows,
    year_from_filename,
    year_of,
)
from app.domains.analytics.points import HistoricalFormatError, Point

EXPECTED = "CONTROL GENERAL"
SNAPSHOT_AT = date(2026, 10, 31)
TARGET_COLUMNS = {"2027": "target", "2027 CONSERVADOR": "target_conservative"}


def load_control_general(content: bytes, filename: str) -> list[Point]:
    wb = open_workbook(content, EXPECTED)
    year = year_from_filename(filename, 2026)
    points: list[Point] = []
    points += _proy(sheet_rows(wb, "PROY", EXPECTED))
    points += _resultados(sheet_rows(wb, "RESUTADOS", EXPECTED), year)
    points += _prestamos(sheet_rows(wb, "PRESTAMOS", EXPECTED))
    points += _inversiones(sheet_rows(wb, "INVERSIONES", EXPECTED))
    if not points:
        raise HistoricalFormatError("El Excel de CONTROL GENERAL no trae cifras que cargar.")
    return points


def _block(rows: list[tuple], title: str) -> tuple[dict[str, int], dict[int, int]]:
    """Bloque cuyo col A es `title`: {etiqueta de año/columna → col} y {mes → fila}."""
    start = next((i for i, row in enumerate(rows) if norm(cell(row, 1)) == title), None)
    if start is None:
        raise HistoricalFormatError(f"La hoja PROY no tiene el bloque «{title}».")
    header = rows[start]
    columns: dict[str, int] = {}
    for j, value in enumerate(header, start=1):
        if j == 1 or value is None:
            continue
        label = norm(value)
        if label in ("%", "DIFERENCIA", "PORCENTAJE"):
            continue
        if year_of(value) is not None:
            columns[label if label in TARGET_COLUMNS else str(year_of(value))] = j
    months: dict[int, int] = {}
    for i in range(start + 1, min(start + 14, len(rows))):
        month = month_of(cell(rows[i], 1))
        if month is None:
            break
        months[month] = i
    return columns, months


def _proy(rows: list[tuple]) -> list[Point]:
    sales_cols, sales_rows = _block(rows, "VENTAS")
    patients_cols, patients_rows = _block(rows, "NO. PACIENTES")
    points: list[Point] = []
    for label, col in sales_cols.items():
        if label in TARGET_COLUMNS:
            for month, i in sales_rows.items():
                amount = money(cell(rows[i], col))
                if amount is not None:
                    points.append(Point("sales_target", TARGET_COLUMNS[label], date(2027, month, 1), "month", amount))
            continue
        year = int(label)
        pcol = patients_cols.get(label)
        for month, i in sales_rows.items():
            prow = patients_rows.get(month)
            patients = money(cell(rows[prow], pcol)) if (pcol and prow is not None) else None
            if patients is None:
                continue  # sin pacientes: proyección (o año sin conteo)
            amount = money(cell(rows[i], col))
            if amount is None:
                continue
            period = date(year, month, 1)
            points.append(Point("sales_monthly", "net_sales", period, "month", amount))
            points.append(Point("sales_monthly", "patients", period, "month", patients))
    return points


def _resultados(rows: list[tuple], year: int) -> list[Point]:
    header_index = next((i for i, row in enumerate(rows) if sum(month_of(v) is not None for v in row) >= 6), None)
    if header_index is None:
        raise HistoricalFormatError("La hoja RESUTADOS no tiene la fila de meses.")
    month_cols = {j: month_of(v) for j, v in enumerate(rows[header_index], start=1) if month_of(v) is not None}
    points: list[Point] = []
    in_banks = False
    for row in rows[header_index + 1 :]:
        label_b, label_c = norm(cell(row, 2)), norm(cell(row, 3))
        if label_b == "CAJA":
            name, in_banks = "CAJA", False
        elif label_b == "BANCOS":
            in_banks = True
            continue
        elif in_banks and label_c and label_c != "TOTAL":
            name = str(cell(row, 3)).strip()
        elif in_banks and label_c == "TOTAL":
            break
        elif norm(cell(row, 1)):
            in_banks = False
            continue
        else:
            continue
        for col, month in month_cols.items():
            amount = money(cell(row, col))
            if amount is None:
                continue
            points.append(Point("balance_monthly", "balance", date(year, month, 1), "month", amount, account_label=name))
    return points


def _prestamos(rows: list[tuple]) -> list[Point]:
    points: list[Point] = []
    for row in rows:
        name = cell(row, 2)
        total = money(cell(row, 3))
        if not norm(name) or total is None or norm(name) in ("TOTAL", "TOTALES"):
            continue
        points.append(Point("snapshot", "loan_balance", SNAPSHOT_AT, "snapshot", total, account_label=str(name).strip()))
    return points


def _inversiones(rows: list[tuple]) -> list[Point]:
    anchor = None
    for i, row in enumerate(rows):
        for j, value in enumerate(row, start=1):
            if norm(value) == "CONCENTRADO GENERAL":
                anchor = (i, j)
                break
        if anchor:
            break
    if anchor is None:
        raise HistoricalFormatError("La hoja INVERSIONES no tiene el bloque «CONCENTRADO GENERAL».")
    start, col = anchor
    points: list[Point] = []
    for row in rows[start + 1 :]:
        name = cell(row, col)
        if not norm(name):
            if points:
                break
            continue
        if norm(name) == "TOTAL":
            break
        amount = money(cell(row, col + 1))
        if amount is None:
            continue
        points.append(Point("snapshot", "investment", SNAPSHOT_AT, "snapshot", amount, unit_label=str(name).strip()))
    return points
