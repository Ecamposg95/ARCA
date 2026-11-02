"""Conversión de celdas a valores: dinero y fechas como vienen en Excel, CSV y Toronja."""

from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal, InvalidOperation

_NON_NUMERIC = re.compile(r"[^0-9.\-]")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y")


def clean_text(value) -> str:
    """Celda a texto: sin `&nbsp;`, saltos ni espacios dobles."""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_money(value) -> Decimal:
    """"$ 1,240.00", "1240", "-350", "(120.50)" y "$ -" (cero). Texto → ValueError."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("No es un monto.")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = clean_text(value)
    if text in ("", "-", "$ -", "$-", "$"):
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    # "1.240,00" (europeo): el último separador es el decimal; "1,240" sola es miles.
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    digits = _NON_NUMERIC.sub("", text)
    if digits in ("", "-", ".", "-."):
        raise ValueError(f"No es un monto: {text}")
    try:
        amount = Decimal(digits)
    except InvalidOperation as exc:
        raise ValueError(f"No es un monto: {text}") from exc
    return -amount if negative and amount > 0 else amount


def parse_date(value) -> date_type:
    """ISO, `DD/MM/AAAA`, `DD-MM-AAAA` y fechas reales de Excel. Otra cosa → ValueError."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_type):
        return value
    text = clean_text(value)
    if not text:
        raise ValueError("Falta la fecha.")
    # "2026-10-07 09:30:00" y el ISO "2026-10-07T00:00:00" de una celda de Excel.
    head = re.split(r"[ T]", text)[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"No es una fecha: {text}")
