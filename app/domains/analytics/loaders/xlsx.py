"""Utilidades comunes para leer los xlsx del histórico."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

from app.domains.analytics.points import HistoricalFormatError

MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}  # fmt: skip
CENT = Decimal("0.01")


def open_workbook(content: bytes, expected: str):
    """Abre el libro en modo sólo lectura con valores calculados; si no es un
    xlsx, levanta `HistoricalFormatError` nombrando lo que se esperaba."""
    try:
        return load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise HistoricalFormatError(f"El archivo no parece el Excel de {expected} (no se pudo abrir como xlsx).") from exc


def sheet_rows(wb, name: str, expected: str) -> list[tuple]:
    if name not in wb.sheetnames:
        raise HistoricalFormatError(f"El Excel de {expected} no tiene la hoja «{name}».")
    return [tuple(row) for row in wb[name].iter_rows(values_only=True)]


def cell(row: tuple, index: int):
    """Celda 1-based; None si no existe."""
    return row[index - 1] if 0 < index <= len(row) else None


def norm(value) -> str:
    """Texto sin acentos, mayúsculas, espacios colapsados; '' si no es texto."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().upper()


def money(value) -> Decimal | None:
    """Número de celda → Decimal a centavos; texto, vacío o error de Excel → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(CENT)
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text or text.startswith("#"):
        return None
    try:
        return Decimal(text).quantize(CENT)
    except InvalidOperation:
        return None


def year_of(value) -> int | None:
    """2024.0, '2025' o '2027 conservador' → el año; otra cosa → None."""
    match = re.match(r"^\s*(20\d{2})(\D|$)", str(value or ""))
    return int(match.group(1)) if match else None


def month_of(value) -> int | None:
    return MONTHS.get(norm(value))


def year_from_filename(filename: str, default: int | None = None) -> int:
    match = re.search(r"(20\d{2})", filename or "")
    return int(match.group(1)) if match else (default or date.today().year)


def as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None
