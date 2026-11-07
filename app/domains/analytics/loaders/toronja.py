"""Toronja (reporte de ventas `.xls` que es HTML) → `sales_daily`.

Reutiliza `parse_toronja`, que ya descarta CLIENTE y ESTUDIOS, y agrega por
día × vendedor (la unidad) × forma de pago antes de devolver nada. Un ticket
cancelado no suma venta pero sí se cuenta en `cancelled`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.domains.analytics.points import HistoricalFormatError, Point
from app.services.dimensions import normalize_alias
from app.services.imports.toronja import ToronjaFormatError, parse_toronja

SUPPORT_VENDOR = "SOPORTE TECNICO DEL SISTEMA"
SHEET = "ventas"
ZERO = Decimal("0")

# métrica por forma de pago ← columnas del ticket que la componen
METHODS = {
    "EFECTIVO": ("cash",),
    "TARJETA": ("debit_card", "credit_card"),
    "TRANSFERENCIA": ("transfer",),
    "CREDITO": ("credit",),
}


def _amount(row: dict, *keys: str) -> Decimal:
    return sum((row.get(key) or ZERO for key in keys), ZERO)


def load_toronja(content: bytes, filename: str) -> list[Point]:
    try:
        rows = parse_toronja(content)
    except ToronjaFormatError as exc:
        raise HistoricalFormatError(str(exc)) from exc

    # (día, unidad) → métrica → valor ; (día, unidad, forma) → valor
    by_unit: dict[tuple[date, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    by_method: dict[tuple[date, str, str], Decimal] = defaultdict(Decimal)

    seen: set[str] = set()
    for row in rows:
        if row.get("error") or row.get("date") is None:
            continue
        folio = (row.get("folio") or "").strip()
        if folio:
            if folio in seen:
                continue  # la misma fila exportada dos veces: igual que el importador
            seen.add(folio)
        vendor = (row.get("vendor") or "").strip()
        if not vendor or normalize_alias(vendor) == SUPPORT_VENDOR:
            continue
        gran_total = _amount(row, "gran_total")
        paid = _amount(row, "cash", "debit_card", "credit_card", "transfer", "credit", "debt")
        if gran_total == 0 and paid == 0 and not row.get("cancelled"):
            continue  # ticket en cero
        key = (row["date"], vendor)
        bucket = by_unit[key]
        if row.get("cancelled"):
            bucket["cancelled"] += 1
            continue
        bucket["tickets"] += 1
        bucket["net_sales"] += gran_total
        bucket["discount"] += _amount(row, "discount")
        bucket["debt"] += _amount(row, "debt")
        if row.get("edited"):
            bucket["edited"] += 1
        for method, columns in METHODS.items():
            amount = _amount(row, *columns)
            if amount:
                by_method[(row["date"], vendor, method)] += amount

    points: list[Point] = []
    for (day, vendor), metrics in sorted(by_unit.items()):
        for metric, amount in metrics.items():
            if amount == 0 and metric not in ("net_sales", "tickets", "cancelled"):
                continue
            if metric in ("net_sales", "tickets") and "tickets" not in metrics:
                continue  # sólo cancelados ese día: no hay venta que reportar
            points.append(Point("sales_daily", metric, day, "day", _money(amount), unit_label=vendor))
    for (day, vendor, method), amount in sorted(by_method.items()):
        points.append(
            Point("sales_daily", "net_sales_by_method", day, "day", _money(amount), unit_label=vendor, payment_method=method)
        )
    if not points:
        raise HistoricalFormatError("El reporte de Toronja no trae tickets que cargar.")
    return points


def _money(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(Decimal("0.01"))
