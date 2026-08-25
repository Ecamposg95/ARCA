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
