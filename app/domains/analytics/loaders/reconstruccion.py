"""Reconstrucción contable (xlsx de Atlas, 21-oct-2026) → estado de resultados
mensual (04), gasto por cuenta × contribuyente × unidad (03) y avance de la
revisión (03, 17, 18) como foto.

El libro exporta todo como texto ('824764.74', '2026-01-01 00:00:00'); se
convierte aquí. Nunca se cargan las pólizas al libro de ONE Finance: esto es
análisis.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal

from app.domains.analytics.loaders.xlsx import as_date, cell, money, month_of, norm, open_workbook, year_from_filename
from app.domains.analytics.points import HistoricalFormatError, Point

EXPECTED = "la reconstrucción contable"
SNAPSHOT_AT = date(2026, 10, 21)
UNASSIGNED = "POR ASIGNAR"
EXPENSE_PREFIXES = ("5", "6", "7")

# concepto (col B, normalizado) → métrica; los de prefijo se comparan con startswith
PNL_EXACT = {
    "TOTAL DE INGRESOS": "revenue",
    "TOTAL COSTO DE VENTAS": "cost_of_sales",
    "UTILIDAD BRUTA": "gross_profit",
    "TOTAL GASTOS DE OPERACION": "operating_expenses",
    "UTILIDAD DE OPERACION": "operating_profit",
}
PNL_PREFIX = {
    "TOTAL RESULTADO INTEGRAL": "financial_result",
    "UTILIDAD ANTES DE SUELDO": "profit_before_partners",
    "UTILIDAD DESPUES DE SUELDO": "profit_after_partners",
}


def load_reconstruccion(content: bytes, filename: str) -> list[Point]:
    wb = open_workbook(content, EXPECTED)
    sheets = {name.split("_", 1)[0]: name for name in wb.sheetnames}
    for number in ("03", "04", "17", "18"):
        if number not in sheets:
            raise HistoricalFormatError(f"El Excel de la reconstrucción no tiene la hoja {number}.")
    rows = {number: [tuple(r) for r in wb[sheets[number]].iter_rows(values_only=True)] for number in ("03", "04", "17", "18")}
    year = year_from_filename(filename, 2026)
    points: list[Point] = []
    points += _estado_resultados(rows["04"], year)
    journal_points, confirmed, pending = _libro_diario(rows["03"])
    points += journal_points
    points.append(_snap("journal_confirmed", confirmed))
    points.append(_snap("journal_pending", pending))
    for prefix, number in (("findings", "17"), ("questions", "18")):
        for status, count in _status_counts(rows[number]).items():
            points.append(_snap(f"{prefix}_{status}", count))
    if not points:
        raise HistoricalFormatError("El Excel de la reconstrucción no trae cifras que cargar.")
    return points


def _snap(metric: str, count: int) -> Point:
    return Point("snapshot", metric, SNAPSHOT_AT, "snapshot", Decimal(count))


def _header(rows: list[tuple], marker: str) -> tuple[int, dict[str, int]]:
    """Fila cuyo alguna celda normalizada es `marker` → (índice, {encabezado normalizado → col})."""
    for i, row in enumerate(rows):
        labels = {norm(v): j for j, v in enumerate(row, start=1) if norm(v)}
        if marker in labels:
            return i, labels
    raise HistoricalFormatError(f"La hoja de la reconstrucción no tiene la columna «{marker}».")


def _estado_resultados(rows: list[tuple], default_year: int) -> list[Point]:
    title = " ".join(str(cell(r, 1) or "") for r in rows[:4])
    match = re.search(r"(20\d{2})", title)
    year = int(match.group(1)) if match else default_year
    header_index, labels = _header(rows, "CUENTA")
    month_cols = {j: month_of(v) for j, v in enumerate(rows[header_index], start=1) if month_of(v) is not None}
    points: list[Point] = []
    for row in rows[header_index + 1 :]:
        concept = norm(cell(row, 2))
        metric = PNL_EXACT.get(concept) or next((m for p, m in PNL_PREFIX.items() if concept.startswith(p)), None)
        if metric is None:
            continue
        for col, month in month_cols.items():
            amount = money(cell(row, col))
            if amount is not None:
                points.append(Point("pnl_monthly", metric, date(year, month, 1), "month", amount))
    return points


def _parse_date(value) -> date | None:
    parsed = as_date(value)
    if parsed is not None:
        return parsed
    text = str(value or "").strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _libro_diario(rows: list[tuple]) -> tuple[list[Point], int, int]:
    header_index, labels = _header(rows, "POLIZA")
    col = {
        "date": labels.get("FECHA"),
        "code": labels.get("CUENTA DE CARGO"),
        "name": labels.get("NOMBRE CUENTA DE CARGO"),
        "amount": next((j for k, j in labels.items() if k.startswith("MONTO")), None),
        "entity": next((j for k, j in labels.items() if k.startswith("ENTIDAD")), None),
        "unit": labels.get("UNIDAD DE NEGOCIO"),
        "status": labels.get("ESTATUS"),
    }
    missing = [k for k, v in col.items() if v is None]
    if missing:
        raise HistoricalFormatError("La hoja 03 de la reconstrucción no tiene las columnas: " + ", ".join(missing) + ".")

    totals: dict[tuple, Decimal] = defaultdict(Decimal)
    names: dict[str, str] = {}
    confirmed = pending = 0
    for row in rows[header_index + 1 :]:
        if not norm(cell(row, 1)):
            continue
        if norm(cell(row, col["status"])) == "CONFIRMADO":
            confirmed += 1
        else:
            pending += 1
        code = str(cell(row, col["code"]) or "").strip()
        when = _parse_date(cell(row, col["date"]))
        amount = money(cell(row, col["amount"]))
        if not code.startswith(EXPENSE_PREFIXES) or when is None or amount is None:
            continue
        entity = str(cell(row, col["entity"]) or "").strip() or None
        if entity and norm(entity) == UNASSIGNED:
            entity = None
        unit = str(cell(row, col["unit"]) or "").strip() or None
        names.setdefault(code, str(cell(row, col["name"]) or "").strip())
        totals[(when.replace(day=1), code, entity, unit)] += amount

    points = [
        Point(
            "expense_monthly",
            "amount",
            period,
            "month",
            amount,
            unit_label=unit,
            entity_label=entity,
            account_code=code,
            account_label=names.get(code) or None,
        )
        for (period, code, entity, unit), amount in sorted(totals.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or "", kv[0][3] or ""))
    ]
    return points, confirmed, pending


def _status_counts(rows: list[tuple]) -> dict[str, int]:
    header_index, labels = _header(rows, "ESTATUS")
    status_col = labels["ESTATUS"]
    counts: Counter[str] = Counter()
    for row in rows[header_index + 1 :]:
        if not norm(cell(row, 1)):
            continue
        status = norm(cell(row, status_col))
        if status:
            counts[re.sub(r"[^A-Z0-9]+", "_", status).strip("_").lower()] += 1
    return dict(counts)
