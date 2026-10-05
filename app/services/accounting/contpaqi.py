"""Pólizas en el layout de texto de CONTPAQi Contabilidad ("Cargado de pólizas").

Un renglón P por póliza y un renglón M por movimiento, de ancho fijo y con los
campos separados por un espacio.

OJO: CONTPAQi no publica este formato. Los anchos salen de una referencia
pública de una versión antigua y NO están verificados contra el CONTPAQi de un
contador real (las versiones recientes usan renglones M1). Por eso el layout es
una tabla: ajustarlo a una muestra real ("bajado de pólizas") es editar
HEADER_LAYOUT y MOVEMENT_LAYOUT, no la lógica.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ENCODING = "cp1252"  # Windows-1252: lo que lee un programa de Windows
NEWLINE = "\r\n"

KIND_CODES = {"INGRESO": "1", "EGRESO": "2", "DIARIO": "3"}
SIDE_DEBIT = "0"
SIDE_CREDIT = "1"
ORIGIN_SYSTEM = "11"


@dataclass(frozen=True)
class Field:
    name: str
    width: int
    align: str = "left"  # left | right


HEADER_LAYOUT = (
    Field("mark", 2),
    Field("date", 8),
    Field("kind", 4, "right"),
    Field("folio", 9, "right"),
    Field("clase", 1),
    Field("diario", 10),
    Field("concept", 100),
    Field("origin", 2, "right"),
    Field("printed", 1),
    Field("adjust", 1),
)
MOVEMENT_LAYOUT = (
    Field("mark", 2),
    Field("account", 30),
    Field("reference", 10),
    Field("side", 1),
    Field("amount", 20),
    Field("diario", 10),
    Field("foreign", 20),
    Field("concept", 100),
)


def _width(layout: tuple[Field, ...]) -> int:
    return sum(field.width for field in layout) + len(layout) - 1


HEADER_WIDTH = _width(HEADER_LAYOUT)
MOVEMENT_WIDTH = _width(MOVEMENT_LAYOUT)


@dataclass(frozen=True)
class Movement:
    account: str
    debit: Decimal
    credit: Decimal
    concept: str


@dataclass(frozen=True)
class Voucher:
    folio: str  # folio de ARCA: Ig-2026-09-0007
    kind: str  # INGRESO | EGRESO | DIARIO
    date: date
    concept: str
    movements: tuple[Movement, ...]


class UnbalancedVoucher(ValueError):
    """Una póliza que no cuadra detiene el export completo."""


def _text(value: str | None) -> str:
    """Una sola línea y sólo caracteres que Windows-1252 puede representar."""
    flat = " ".join((value or "").split())
    return flat.encode(ENCODING, errors="replace").decode(ENCODING)


def _line(layout: tuple[Field, ...], values: dict[str, str]) -> str:
    cells = []
    for field in layout:
        value = _text(values[field.name])[: field.width]
        cells.append(value.rjust(field.width) if field.align == "right" else value.ljust(field.width))
    return " ".join(cells)


def _folio_number(folio: str) -> str:
    """Ig-2026-09-0007 → 7: CONTPAQi quiere el consecutivo, no el folio completo."""
    match = re.search(r"(\d+)$", folio)
    return str(int(match.group(1))) if match else "0"


def _reference(folio: str) -> str:
    """El folio de ARCA sin el año, para que quepa en 10: Ig-2026-09-0007 → Ig-09-0007."""
    parts = folio.split("-")
    return "-".join((parts[0], *parts[2:])) if len(parts) == 4 else folio


def render(vouchers: Iterable[Voucher]) -> str:
    lines: list[str] = []
    for voucher in vouchers:
        debit = sum((m.debit for m in voucher.movements), Decimal("0"))
        credit = sum((m.credit for m in voucher.movements), Decimal("0"))
        if debit != credit:
            raise UnbalancedVoucher(
                f"La póliza {voucher.folio} no cuadra: cargos {debit:.2f}, abonos {credit:.2f}."
            )
        lines.append(
            _line(
                HEADER_LAYOUT,
                {
                    "mark": "P",
                    "date": voucher.date.strftime("%Y%m%d"),
                    "kind": KIND_CODES.get(voucher.kind, KIND_CODES["DIARIO"]),
                    "folio": _folio_number(voucher.folio),
                    "clase": "1",
                    "diario": "0",
                    "concept": voucher.concept,
                    "origin": ORIGIN_SYSTEM,
                    "printed": "0",
                    "adjust": "0",
                },
            )
        )
        reference = _reference(voucher.folio)
        for movement in voucher.movements:
            for side, amount in ((SIDE_DEBIT, movement.debit), (SIDE_CREDIT, movement.credit)):
                if amount <= 0:
                    continue
                lines.append(
                    _line(
                        MOVEMENT_LAYOUT,
                        {
                            "mark": "M",
                            "account": movement.account,
                            "reference": reference,
                            "side": side,
                            "amount": f"{amount:.2f}",
                            "diario": "0",
                            "foreign": "0.0",
                            "concept": movement.concept,
                        },
                    )
                )
    return "".join(line + NEWLINE for line in lines)
