"""Control de Efectivo (una hoja por mes) → `cash_daily` de la caja central.

Se lee la tabla de la derecha (Fecha | Ingresos día | Egresos día | Saldo
cierre día), localizada por su encabezado. Un mes sin ningún ingreso ni
egreso se omite: su saldo sólo arrastra el anterior o es la plantilla vacía.
"""

from __future__ import annotations

from datetime import datetime

from app.domains.analytics.loaders.xlsx import as_date, cell, month_of, money, norm, open_workbook
from app.domains.analytics.points import HistoricalFormatError, Point

EXPECTED = "Control de Efectivo"
ACCOUNT = "Caja central"
METRICS = {"INGRESOS DIA": "inflows", "EGRESOS DIA": "outflows", "SALDO CIERRE DIA": "closing_balance"}


def _day(value):
    parsed = as_date(value)
    if parsed is not None:
        return parsed
    try:
        return datetime.strptime(str(value or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_efectivo(content: bytes, filename: str) -> list[Point]:
    wb = open_workbook(content, EXPECTED)
    month_sheets = [name for name in wb.sheetnames if month_of(name) is not None]
    if not month_sheets:
        raise HistoricalFormatError("El Excel de Control de Efectivo no tiene hojas de mes (Enero…Diciembre).")
    points: list[Point] = []
    for name in month_sheets:
        rows = [tuple(r) for r in wb[name].iter_rows(values_only=True)]
        header = next(
            ((i, row) for i, row in enumerate(rows) if any(norm(v) == "SALDO CIERRE DIA" for v in row)),
            None,
        )
        if header is None:
            continue
        header_index, header_row = header
        cols = {norm(v): j for j, v in enumerate(header_row, start=1) if norm(v)}
        # La columna Fecha de la tabla derecha es la última «FECHA» antes de Ingresos día.
        date_col = max(j for j, v in enumerate(header_row, start=1) if norm(v) == "FECHA" and j < cols["SALDO CIERRE DIA"])
        month_points: list[Point] = []
        moved = False
        for row in rows[header_index + 1 :]:
            day = _day(cell(row, date_col))
            if day is None:
                continue
            for label, metric in METRICS.items():
                amount = money(cell(row, cols.get(label, 0)))
                if amount is None:
                    continue
                if metric != "closing_balance" and amount != 0:
                    moved = True
                month_points.append(Point("cash_daily", metric, day, "day", amount, account_label=ACCOUNT))
        if moved:
            points += month_points
    if not points:
        raise HistoricalFormatError("El Excel de Control de Efectivo no trae ningún mes con movimientos.")
    return points
