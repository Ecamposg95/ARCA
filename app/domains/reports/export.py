"""Exportación de reportes a CSV.

Deliberadamente sin librerías de PDF: agregar weasyprint o reportlab a la imagen
cuesta decenas de megas y trae dependencias de sistema. El CSV lo abre Excel
—que es lo que el contador realmente quiere— y para el PDF con membrete basta la
impresión del navegador, que ya respeta el diseño de la pantalla.
"""

from __future__ import annotations

import csv
import io
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
