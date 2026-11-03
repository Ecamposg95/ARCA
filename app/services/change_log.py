"""Captura de la bitácora de cambios (HU-09).

Uso típico dentro de un service, en la MISMA transacción que la operación:

    before = snapshot(expense)
    ... modificar expense ...
    record_change(db, org_id, expense, "UPDATE", user_id, before=before, after=snapshot(expense))

El diff sólo guarda campos que de verdad cambiaron; `updated_at` y demás
marcas técnicas nunca entran. El origen (web, asistente, agente, importación,
autorización) viaja en un contextvar para no tener que pasarlo por cada
firma de service: quien orquesta lo fija con `with change_source("import")`.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Iterator

from sqlalchemy.orm import Session

from app.models.change_log import ChangeLog

# Campos con significado de negocio por tipo de registro. Lo que no está aquí
# (subtotales derivados, timestamps, quién canceló…) no se audita como diff.
TRACKED_FIELDS: dict[str, tuple[str, ...]] = {
    "expense": (
        "amount",
        "date",
        "description",
        "category_id",
        "vendor_id",
        "financial_account_id",
        "project_id",
        "payment_method",
        "reference",
        "notes",
        "status",
    ),
    "income": (
        "amount",
        "date",
        "description",
        "category_id",
        "customer_id",
        "financial_account_id",
        "project_id",
        "notes",
        "status",
    ),
    "payable": (
        "amount",
        "amount_paid",
        "date",
        "due_date",
        "description",
        "category_id",
        "vendor_id",
        "project_id",
        "notes",
        "status",
    ),
    "receivable": (
        "amount",
        "amount_paid",
        "date",
        "due_date",
        "description",
        "category_id",
        "customer_id",
        "project_id",
        "notes",
        "status",
    ),
    "financial_account": (
        "name",
        "type",
        "institution",
        "last_four",
        "credit_limit",
        "active",
        "business_unit_id",
        "fee_rate",
        "settlement_days",
        "settlement_account_id",
        "opening_balance",
        "opening_status",
        "opening_note",
    ),
    "category": ("name", "kind", "account_code", "active"),
    "proposal": ("status", "kind", "summary"),
}

# Al crear sólo importan los datos que identifican la operación.
CREATE_FIELDS: dict[str, tuple[str, ...]] = {
    "expense": ("amount", "date", "description", "category_id", "vendor_id", "financial_account_id", "status"),
    "income": ("amount", "date", "description", "category_id", "customer_id", "financial_account_id", "status"),
    "payable": ("amount", "date", "due_date", "description", "category_id", "vendor_id", "status"),
    "receivable": ("amount", "date", "due_date", "description", "category_id", "customer_id", "status"),
    "financial_account": ("name", "type", "opening_balance", "institution", "credit_limit"),
}

_TABLE_TO_TYPE = {
    "expenses": "expense",
    "income": "income",
    "incomes": "income",
    "payables": "payable",
    "receivables": "receivable",
    "financial_accounts": "financial_account",
    "categories": "category",
    "agent_proposals": "proposal",
}

_source: ContextVar[str] = ContextVar("change_source", default="web")


@contextmanager
def change_source(source: str) -> Iterator[None]:
    """Todo lo registrado dentro del bloque lleva este origen."""
    token = _source.set(source)
    try:
        yield
    finally:
        _source.reset(token)


def current_source() -> str:
    return _source.get()


def entity_type_of(entity: Any) -> str:
    table = getattr(entity, "__tablename__", None)
    entity_type = _TABLE_TO_TYPE.get(table or "")
    if entity_type is None:
        raise ValueError(f"No hay bitácora definida para {table!r}.")
    return entity_type


def serialize(value: Any) -> Any:
    """JSON estable: Decimal → str (nunca float), fechas → ISO."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _same(a: Any, b: Any) -> bool:
    # Decimal("1200") y Decimal("1200.00") son el mismo monto aunque su str difiera.
    if isinstance(a, Decimal) or isinstance(b, Decimal):
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except Exception:  # noqa: BLE001 — valores no numéricos: compara tal cual
            return a == b
    return a == b


def snapshot(entity: Any, fields: Iterable[str] | None = None) -> dict[str, Any]:
    """Foto de los campos auditables de un objeto ORM (valores crudos, sin serializar)."""
    if fields is None:
        fields = TRACKED_FIELDS[entity_type_of(entity)]
    return {field: getattr(entity, field, None) for field in fields}


def diff(before: dict | None, after: dict | None) -> dict[str, dict[str, Any]]:
    before = before or {}
    after = after or {}
    changes: dict[str, dict[str, Any]] = {}
    for field in list(dict.fromkeys([*before.keys(), *after.keys()])):
        old, new = before.get(field), after.get(field)
        if _same(old, new):
            continue
        changes[field] = {"old": serialize(old), "new": serialize(new)}
    return changes


def record_change(
    db: Session,
    org_id: str,
    entity: Any,
    action: str,
    user_id: str | None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    source: str | None = None,
    entity_type: str | None = None,
) -> ChangeLog | None:
    """Agrega un evento a la bitácora sin hacer commit (va con la operación).

    Un UPDATE sin cambios reales no deja rastro: guardar "nada cambió" sólo
    ensucia el historial. CREATE, CANCEL, PAY y las revisiones sí se guardan
    siempre: el hecho en sí es lo relevante.
    """
    entity_type = entity_type or entity_type_of(entity)
    if action == "CREATE" and after is None:
        after = snapshot(entity, CREATE_FIELDS.get(entity_type) or TRACKED_FIELDS[entity_type])
    changes = diff(before, after)
    if action == "UPDATE" and not changes:
        return None
    event = ChangeLog(
        organization_id=org_id,
        entity_type=entity_type,
        entity_id=entity.id,
        action=action,
        changes=changes,
        reason=(reason or "").strip() or None,
        user_id=user_id,
        source=source or current_source(),
    )
    db.add(event)
    return event
