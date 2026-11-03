"""Filtros y descarga de las listas de operaciones (gastos, ingresos, movimientos).

Cada dominio tiene UNA función que arma el query filtrado; la lista paginada y
la descarga a Excel la usan igual, así que lo que el usuario ve es lo que baja.
Aquí vive lo común: los parámetros, el tope de renglones y el archivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from fastapi import HTTPException, Query, Response

from app.domains.reports.export import to_csv, to_xlsx

# Tope de renglones por descarga. Más que esto no lo revisa una persona y
# armarlo en memoria compromete al servidor: que acote fechas o filtros.
MAX_EXPORT_ROWS = 50_000

EXPORT_HEADERS = [
    "Fecha",
    "Concepto",
    "Categoría",
    "Cuenta",
    "Unidad",
    "Contribuyente",
    "Proveedor/Cliente",
    "Forma de pago",
    "Estado",
    "Subtotal",
    "IVA",
    "Total",
    "Registró",
    "Referencia",
]
MONEY_COLUMNS = {9, 10, 11}

PAYMENT_METHOD_LABELS = {
    "EFECTIVO": "Efectivo",
    "TRANSFERENCIA": "Transferencia",
    "TARJETA_DEBITO": "Tarjeta de débito",
    "TARJETA_CREDITO": "Tarjeta de crédito",
    "TARJETA": "Tarjeta",
    "DOMICILIACION": "Domiciliación",
    "CHEQUE": "Cheque",
    "PASARELA": "Pasarela de pago",
    "OTRO": "Otro",
}


@dataclass
class OperationFilters:
    """Los filtros de una lista de operaciones. Todos opcionales: sin ninguno,
    el query es idéntico al de siempre."""

    status: str | None = None
    start: date_type | None = None
    end: date_type | None = None
    q: str | None = None
    category_id: str | None = None
    project_id: str | None = None
    business_unit_id: str | None = None
    fiscal_entity_id: str | None = None
    financial_account_id: str | None = None
    payment_method: str | None = None
    created_by: str | None = None
    contact: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


def operation_filters(
    status: str | None = Query(default=None, pattern="^(PENDING|PAID|CANCELLED)$"),
    start: date_type | None = None,
    end: date_type | None = None,
    q: str | None = Query(default=None, max_length=200),
    category_id: str | None = None,
    project_id: str | None = None,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
    financial_account_id: str | None = None,
    payment_method: str | None = Query(default=None, max_length=30),
    created_by: str | None = Query(default=None, max_length=36),
    contact: str | None = Query(default=None, max_length=36, description="Proveedor o cliente (id)."),
    min_amount: Decimal | None = Query(default=None, ge=0, allow_inf_nan=False),
    max_amount: Decimal | None = Query(default=None, ge=0, allow_inf_nan=False),
) -> OperationFilters:
    """Dependencia de FastAPI: los mismos parámetros para lista y descarga."""
    return OperationFilters(
        status=status,
        start=start,
        end=end,
        q=q,
        category_id=category_id,
        project_id=project_id,
        business_unit_id=business_unit_id,
        fiscal_entity_id=fiscal_entity_id,
        financial_account_id=financial_account_id,
        payment_method=payment_method,
        created_by=created_by,
        contact=contact,
        min_amount=min_amount,
        max_amount=max_amount,
    )


def check_export_size(query) -> None:
    """400 en español si la descarga rebasa el tope. Se cuenta antes de cargar nada."""
    total = query.order_by(None).count()
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La descarga tendría {total:,} renglones y el máximo es {MAX_EXPORT_ROWS:,}. "
                "Acota el rango de fechas o agrega filtros."
            ),
        )


def export_filename(prefix: str, start: date_type | None, end: date_type | None, extension: str) -> str:
    """`gastos_2026-11-01_a_2026-11-30.xlsx`; sin fechas, hasta hoy."""
    if start and end:
        span = f"{start.isoformat()}_a_{end.isoformat()}"
    elif start:
        span = f"desde_{start.isoformat()}"
    else:
        span = f"al_{(end or date_type.today()).isoformat()}"
    return f"{prefix}_{span}.{extension}"


def export_response(
    *,
    rows: list[list],
    total_row: list,
    file_format: str,
    prefix: str,
    sheet_title: str,
    start: date_type | None,
    end: date_type | None,
    headers: list[str] = EXPORT_HEADERS,
    money_columns: set[int] = MONEY_COLUMNS,
) -> Response:
    filename = export_filename(prefix, start, end, file_format)
    disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if file_format == "csv":
        csv_rows = [[value.isoformat() if isinstance(value, date_type) else value for value in row] for row in rows]
        return Response(
            content=to_csv(headers, [*csv_rows, total_row]),
            media_type="text/csv; charset=utf-8",
            headers=disposition,
        )
    return Response(
        content=to_xlsx(
            headers,
            rows,
            sheet_title=sheet_title,
            money_columns=money_columns,
            total_row=total_row,
        ),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=disposition,
    )


def money_total_row(
    rows: list[list],
    *,
    status_index: int = 8,
    money_columns: set[int] = MONEY_COLUMNS,
    width: int = len(EXPORT_HEADERS),
    cancelled_label: str = "Cancelado",
) -> list:
    """Renglón de totales. Lo cancelado se lista (así lo muestra la pantalla
    en "Todos") pero no se suma: no movió dinero."""
    totals: list = [None] * width
    has_cancelled = False
    for row in rows:
        if row[status_index] == cancelled_label:
            has_cancelled = True
            continue
        for index in money_columns:
            if row[index] is not None:
                totals[index] = (totals[index] or Decimal("0")) + row[index]
    for index in money_columns:
        if totals[index] is None:
            totals[index] = Decimal("0")
    totals[0] = "Total (sin cancelados)" if has_cancelled else "Total"
    return totals


def payment_label(method: str | None) -> str | None:
    if not method:
        return None
    return PAYMENT_METHOD_LABELS.get(method, method)


def name_map(db, model, org_id: str | None, ids) -> dict[str, str]:
    """{id: nombre} en una consulta. Con `org_id`, sólo lo de esa empresa;
    sin él (usuarios), los ids ya vienen de renglones de la empresa."""
    wanted = {key for key in ids if key}
    if not wanted:
        return {}
    query = db.query(model.id, model.name).filter(model.id.in_(wanted))
    if org_id is not None:
        query = query.filter(model.organization_id == org_id)
    return dict(query.all())
