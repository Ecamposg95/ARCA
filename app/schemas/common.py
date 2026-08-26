"""Sobre de paginación canónico Atlas: {items, total, limit, offset}. Único en todo el API."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import func

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def paginate(query, limit: int, offset: int, schema, sum_column=None) -> dict:
    """Aplica limit/offset a un query ya filtrado por organización y serializa.

    `sum_column` agrega el total monetario de TODO el filtro (no sólo de la
    página): mostrar la suma de una página sería engañoso.
    """
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    page = {
        "items": [schema.model_validate(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
    if sum_column is not None:
        page["total_amount"] = query.with_entities(
            func.coalesce(func.sum(sum_column), 0)
        ).order_by(None).scalar()
    return page


def apply_sort(query, sort: str | None, allowed: dict, default: tuple):
    """Orden por columna con whitelist explícita.

    `sort="-amount"` ordena descendente. Un campo fuera de la whitelist se
    rechaza con 422: ordenarse por columnas arbitrarias expondría detalles
    internos y permitiría sondear el modelo. El orden por defecto del recurso
    se conserva como desempate para que la paginación sea estable.
    """
    from fastapi import HTTPException

    if not sort:
        return query.order_by(*default)
    descending = sort.startswith("-")
    field = sort[1:] if descending else sort
    column = allowed.get(field)
    if column is None:
        raise HTTPException(
            status_code=422,
            detail=f"No se puede ordenar por '{field}'. Campos válidos: {', '.join(sorted(allowed))}.",
        )
    return query.order_by(column.desc() if descending else column.asc(), *default)
