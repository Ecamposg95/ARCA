"""Lector de archivos tabulares: CSV (`,` o `;`, UTF-8 o latin-1) y XLSX.

Devuelve columnas y filas crudas como diccionarios `{columna: valor}`; nadie
interpreta aquí qué es fecha o monto: eso lo decide el mapeo del usuario en
`app/domains/imports/service.py`. `openpyxl` se importa sólo al leer XLSX.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.services.imports.values import clean_text


class TabularFormatError(ValueError):
    """El archivo no se pudo leer como tabla."""


@dataclass
class Table:
    columns: list[str]
    rows: list[dict]  # {columna: valor crudo}; `_row_number` = fila del archivo (1 = encabezado)
    sheets: list[str] = field(default_factory=list)
    sheet: str | None = None


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _header(cells: list) -> list[str]:
    """Encabezados únicos y no vacíos: una columna sin nombre se llama 'Columna N'."""
    names: list[str] = []
    for index, raw in enumerate(cells, start=1):
        name = clean_text(raw) or f"Columna {index}"
        base, suffix = name, 2
        while name in names:
            name = f"{base} ({suffix})"
            suffix += 1
        names.append(name)
    return names


def _rows(columns: list[str], raw_rows, first_row_number: int) -> list[dict]:
    rows: list[dict] = []
    for offset, cells in enumerate(raw_rows):
        values = list(cells)
        if not any(clean_text(v) for v in values):
            continue
        row = {col: (values[i] if i < len(values) else None) for i, col in enumerate(columns)}
        row["_row_number"] = first_row_number + offset
        rows.append(row)
    return rows


def read_csv(content: bytes) -> Table:
    text = _decode(content)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    lines = [line for line in reader]
    header_index = next((i for i, line in enumerate(lines) if any(clean_text(c) for c in line)), None)
    if header_index is None:
        raise TabularFormatError("El archivo está vacío.")
    columns = _header(lines[header_index])
    return Table(columns=columns, rows=_rows(columns, lines[header_index + 1 :], header_index + 2))


def read_xlsx(content: bytes, sheet: str | None = None) -> Table:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise TabularFormatError("Este servidor no puede leer XLSX (falta openpyxl).") from exc
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise TabularFormatError("El archivo no es un XLSX válido.") from exc
    sheets = list(workbook.sheetnames)
    if not sheets:
        raise TabularFormatError("El archivo no tiene hojas.")
    if sheet and sheet not in sheets:
        raise TabularFormatError(f"El archivo no tiene una hoja llamada {sheet}.")
    worksheet = workbook[sheet or sheets[0]]
    lines = [list(row) for row in worksheet.iter_rows(values_only=True)]
    header_index = next((i for i, line in enumerate(lines) if any(clean_text(c) for c in line)), None)
    if header_index is None:
        raise TabularFormatError("La hoja está vacía.")
    columns = _header(lines[header_index])
    return Table(
        columns=columns,
        rows=_rows(columns, lines[header_index + 1 :], header_index + 2),
        sheets=sheets,
        sheet=sheet or sheets[0],
    )


def read_table(content: bytes, filename: str, sheet: str | None = None) -> Table:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return read_xlsx(content, sheet)
    if name.endswith(".xls"):
        # Un .xls real (binario) no se lee; el de Toronja es HTML y tiene su propio formato.
        raise TabularFormatError("Guarda el archivo como .xlsx o .csv; el formato .xls antiguo no se lee.")
    if content[:4] == b"PK\x03\x04":
        return read_xlsx(content, sheet)
    return read_csv(content)
