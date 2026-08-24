"""Sección Contabilidad (task pack §25) — solo OWNER / ADMIN / ACCOUNTANT."""

from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.organization import ACCOUNTING_ROLES
from app.security.deps import get_current_org_id, require_role
from app.services.accounting.engine import trial_balance as compute_trial_balance

router = APIRouter(
    prefix="/accounting",
    tags=["accounting"],
    dependencies=[Depends(require_role(ACCOUNTING_ROLES))],
)


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    type: str
    parent_id: str | None
    active: bool


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    debit: Decimal
    credit: Decimal
    description: str | None


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date_type
    description: str
    reference: str | None
    source_type: str | None
    source_id: str | None
    status: str
    lines: list[JournalLineRead] = []


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    accounts = (
        db.query(Account)
        .filter(Account.organization_id == org_id)
        .order_by(Account.code)
        .all()
    )
    return [AccountRead.model_validate(account) for account in accounts]


@router.get("/journal-entries")
def list_journal_entries(
    start: date_type | None = None,
    end: date_type | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(JournalEntry).filter(JournalEntry.organization_id == org_id)
    if start:
        query = query.filter(JournalEntry.date >= start)
    if end:
        query = query.filter(JournalEntry.date <= end)
    query = query.order_by(JournalEntry.date.desc(), JournalEntry.created_at.desc())

    total = query.count()
    entries = query.limit(limit).offset(offset).all()
    entry_ids = [entry.id for entry in entries]
    lines_by_entry: dict[str, list[JournalLineRead]] = {}
    if entry_ids:
        lines = (
            db.query(JournalEntryLine)
            .filter(JournalEntryLine.journal_entry_id.in_(entry_ids))
            .all()
        )
        for line in lines:
            lines_by_entry.setdefault(line.journal_entry_id, []).append(JournalLineRead.model_validate(line))

    items = []
    for entry in entries:
        item = JournalEntryRead.model_validate(entry)
        item.lines = lines_by_entry.get(entry.id, [])
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/trial-balance")
def trial_balance(
    as_of: date_type | None = None,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    rows = compute_trial_balance(db, org_id, as_of)
    return {
        "rows": rows,
        "total_debit": sum((row["debit"] for row in rows), Decimal("0")),
        "total_credit": sum((row["credit"] for row in rows), Decimal("0")),
    }
