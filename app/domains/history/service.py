"""Lectura de la bitácora: filtros, nombres de usuario y referencias legibles.

Todo se resuelve en lote y SIEMPRE filtrado por organización: una referencia
a una categoría o cuenta de otra empresa nunca se traduce a su nombre.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.domains.history.schemas import FieldChange, HistoryEvent
from app.models.agent import AgentProposal
from app.models.business_unit import BusinessUnit
from app.models.category import Category
from app.models.change_log import ChangeLog
from app.models.contact import Customer, Vendor
from app.models.expense import Expense
from app.models.financial_account import FinancialAccount
from app.models.fiscal_entity import FiscalEntity
from app.models.income import Income
from app.models.payable import Payable
from app.models.project import Project
from app.models.receivable import Receivable
from app.models.user import User

# campo → (etiqueta, tipo, modelo referido)
FIELD_META: dict[str, tuple[str, str, type | None]] = {
    "amount": ("Monto", "money", None),
    "amount_paid": ("Pagado", "money", None),
    "opening_balance": ("Saldo inicial", "money", None),
    "credit_limit": ("Límite de crédito", "money", None),
    "date": ("Fecha", "date", None),
    "due_date": ("Vencimiento", "date", None),
    "payment_date": ("Fecha del pago", "date", None),
    "description": ("Concepto", "text", None),
    "name": ("Nombre", "text", None),
    "summary": ("Resumen", "text", None),
    "notes": ("Notas", "text", None),
    "reference": ("Referencia", "text", None),
    "institution": ("Institución", "text", None),
    "last_four": ("Últimos 4 dígitos", "text", None),
    "type": ("Tipo", "text", None),
    "kind": ("Tipo", "text", None),
    "account_code": ("Cuenta contable", "text", None),
    "payment_method": ("Forma de pago", "text", None),
    "settlement_days": ("Días para liquidar", "text", None),
    "fee_rate": ("Comisión", "rate", None),
    "status": ("Estado", "status", None),
    "active": ("Activa", "bool", None),
    "category_id": ("Categoría", "ref", Category),
    "financial_account_id": ("Cuenta", "ref", FinancialAccount),
    "payment_account_id": ("Cuenta del pago", "ref", FinancialAccount),
    "settlement_account_id": ("Banco donde liquida", "ref", FinancialAccount),
    "vendor_id": ("Proveedor", "ref", Vendor),
    "customer_id": ("Cliente", "ref", Customer),
    "project_id": ("Proyecto", "ref", Project),
    "business_unit_id": ("Unidad", "ref", BusinessUnit),
    "fiscal_entity_id": ("Contribuyente", "ref", FiscalEntity),
}

# tipo de registro → (modelo, columna que lo nombra)
ENTITY_MODELS: dict[str, tuple[type, str]] = {
    "expense": (Expense, "description"),
    "income": (Income, "description"),
    "payable": (Payable, "description"),
    "receivable": (Receivable, "description"),
    "financial_account": (FinancialAccount, "name"),
    "category": (Category, "name"),
    "proposal": (AgentProposal, "summary"),
}


def _names(db: Session, org_id: str, model: type, ids: set[str], column: str = "name") -> dict[str, str]:
    if not ids:
        return {}
    rows = (
        db.query(model.id, getattr(model, column))
        .filter(model.organization_id == org_id, model.id.in_(ids))
        .all()
    )
    return {row[0]: row[1] for row in rows}


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def history_page(
    db: Session,
    org_id: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    action: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    query = db.query(ChangeLog).filter(ChangeLog.organization_id == org_id)
    if entity_type:
        query = query.filter(ChangeLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(ChangeLog.entity_id == entity_id)
    if user_id:
        query = query.filter(ChangeLog.user_id == user_id)
    if action:
        query = query.filter(ChangeLog.action == action)
    if start:
        query = query.filter(ChangeLog.created_at >= _start_of(start))
    if end:
        query = query.filter(ChangeLog.created_at < _start_of(end + timedelta(days=1)))

    total = query.count()
    rows = (
        query.order_by(ChangeLog.created_at.desc(), ChangeLog.id.desc()).limit(limit).offset(offset).all()
    )
    return {
        "items": serialize_events(db, org_id, rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def serialize_events(db: Session, org_id: str, rows: list[ChangeLog]) -> list[HistoryEvent]:
    user_ids = {row.user_id for row in rows if row.user_id}
    users = dict(db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()) if user_ids else {}

    # Referencias a resolver, agrupadas por modelo.
    wanted: dict[type, set[str]] = defaultdict(set)
    for row in rows:
        for field, change in (row.changes or {}).items():
            model = FIELD_META.get(field, (None, None, None))[2]
            if model is None:
                continue
            for value in (change.get("old"), change.get("new")):
                if value:
                    wanted[model].add(str(value))
    resolved = {model: _names(db, org_id, model, ids) for model, ids in wanted.items()}

    by_type: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_type[row.entity_type].add(row.entity_id)
    labels: dict[tuple[str, str], str] = {}
    for entity_type, ids in by_type.items():
        spec = ENTITY_MODELS.get(entity_type)
        if spec is None:
            continue
        for entity_id, label in _names(db, org_id, spec[0], ids, spec[1]).items():
            labels[(entity_type, entity_id)] = label

    events: list[HistoryEvent] = []
    for row in rows:
        changes: list[FieldChange] = []
        for field, change in (row.changes or {}).items():
            label, kind, model = FIELD_META.get(field, (field, "text", None))
            names = resolved.get(model, {}) if model else {}
            old, new = change.get("old"), change.get("new")
            changes.append(
                FieldChange(
                    field=field,
                    label=label,
                    kind=kind,
                    old=old,
                    new=new,
                    old_display=names.get(str(old)) if model and old else None,
                    new_display=names.get(str(new)) if model and new else None,
                )
            )
        events.append(
            HistoryEvent(
                id=row.id,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                entity_label=labels.get((row.entity_type, row.entity_id)),
                action=row.action,
                source=row.source,
                reason=row.reason,
                user_id=row.user_id,
                user_name=users.get(row.user_id) if row.user_id else None,
                created_at=row.created_at,
                changes=changes,
            )
        )
    return events
