"""Exportación de reportes y listas a CSV y XLSX.

Deliberadamente sin librerías de PDF: agregar weasyprint o reportlab a la imagen
cuesta decenas de megas y trae dependencias de sistema. El CSV lo abre Excel
—que es lo que el contador realmente quiere— y para el PDF con membrete basta la
impresión del navegador, que ya respeta el diseño de la pantalla.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (Decimal, float)):
        return f"{value:.2f}"
    return str(value)


def to_csv(headers: list[str], rows: list[list]) -> str:
    """CSV con BOM: sin él, Excel en Windows destroza los acentos."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_clean(cell) for cell in row])
    return "﻿" + buffer.getvalue()


MONEY_FORMAT = '"$"#,##0.00;-"$"#,##0.00'
DATE_FORMAT = "dd/mm/yyyy"


def _xlsx_value(value):
    # Excel guarda cifras como doble precisión: a 2 decimales la conversión es
    # exacta para lo que muestra la celda. El Decimal sigue siendo la fuente.
    return float(value) if isinstance(value, Decimal) else value


def to_xlsx(
    headers: list[str],
    rows: list[list],
    *,
    sheet_title: str = "Hoja1",
    money_columns: set[int] = frozenset(),
    total_row: list | None = None,
) -> bytes:
    """XLSX con cifras de verdad: los montos van como número con formato de
    moneda (no como texto), para que el contador sume y filtre en Excel.

    `money_columns` son índices base 0; `total_row` se agrega al final en negritas.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title[:31]
    sheet.append(headers)
    bold = Font(bold=True)
    for cell in sheet[1]:
        cell.font = bold
        cell.fill = PatternFill("solid", fgColor="EEEEEE")

    for row in rows:
        sheet.append([_xlsx_value(value) for value in row])
    last_data_row = sheet.max_row
    if total_row is not None:
        sheet.append([_xlsx_value(value) for value in total_row])
        for cell in sheet[sheet.max_row]:
            cell.font = bold

    widths = [len(str(header)) for header in headers]
    for row in sheet.iter_rows(min_row=2):
        for index, cell in enumerate(row):
            if index in money_columns:
                cell.number_format = MONEY_FORMAT
            elif isinstance(cell.value, date):
                cell.number_format = DATE_FORMAT
            if index < len(widths) and cell.value is not None:
                widths[index] = max(widths[index], min(len(str(cell.value)), 60))
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width + 2

    sheet.freeze_panes = "A2"
    if last_data_row > 1:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_data_row}"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
