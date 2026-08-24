"""Sobre de paginación canónico Atlas: {items, total, limit, offset}. Único en todo el API."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def paginate(query, limit: int, offset: int, schema) -> dict:
    """Aplica limit/offset a un query ya filtrado por organización y serializa."""
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    return {
        "items": [schema.model_validate(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
