from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.expenses import service
from app.domains.expenses.listing import expense_export_rows, filter_expenses
from app.domains.expenses.schemas import ExpenseCancel, ExpenseCreate, ExpensePay, ExpenseRead
from app.models.contact import Vendor
from app.models.expense import Expense
from app.models.organization import WRITE_ROLES
from app.models.project import Project
from app.models.user import User
from app.schemas.common import apply_sort, paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services import approvals
from app.services.listing import (
    OperationFilters,
    check_export_size,
    export_response,
    money_total_row,
    operation_filters,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _vendor_name(db: Session, org_id: str, vendor_id: str | None) -> str | None:
    if not vendor_id:
        return None
    row = db.query(Vendor.name).filter(Vendor.id == vendor_id, Vendor.organization_id == org_id).first()
    return row[0] if row else None


def _expense_summary(
    db: Session, org_id: str, *, amount, vendor_id: str | None, description: str, paying: bool
) -> str:
    verb = "Pago de gasto de" if paying else "Gasto de"
    vendor = _vendor_name(db, org_id, vendor_id)
    recipient = f" a {vendor}" if vendor else ""
    return f"{verb} {approvals.money(amount)}{recipient} · {description.strip()}"


def _get_expense(db: Session, org_id: str, expense_id: str) -> Expense:
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.organization_id == org_id)
        .first()
    )
    if expense is None:
        raise HTTPException(status_code=404, detail="El gasto no existe.")
    return expense


def _sorted(query, sort: str | None):
    return apply_sort(
        query,
        sort,
        {"date": Expense.date, "amount": Expense.amount},
        (Expense.date.desc(), Expense.created_at.desc()),
    )


@router.get("")
def list_expenses(
    filters: OperationFilters = Depends(operation_filters),
    sort: str | None = Query(default=None, max_length=30),
    non_deductible: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = _sorted(filter_expenses(db, org_id, filters, non_deductible=non_deductible), sort)
    return paginate(query, limit, offset, ExpenseRead, sum_column=Expense.amount)


@router.get("/export")
def export_expenses(
    filters: OperationFilters = Depends(operation_filters),
    sort: str | None = Query(default=None, max_length=30),
    non_deductible: bool = Query(default=False),
    file_format: str = Query(default="xlsx", alias="format", pattern="^(xlsx|csv)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Los gastos de la lista, con los mismos filtros, en Excel o CSV."""
    query = _sorted(filter_expenses(db, org_id, filters, non_deductible=non_deductible), sort)
    check_export_size(query)
    rows = expense_export_rows(db, org_id, query)
    return export_response(
        rows=rows,
        total_row=money_total_row(rows),
        file_format=file_format,
        prefix="gastos",
        sheet_title="Gastos",
        start=filters.start,
        end=filters.end,
    )


@router.post("", response_model=ExpenseRead, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership=Depends(require_role(WRITE_ROLES)),
):
    # Un gasto que nace pendiente no mueve dinero: se evalúa cuando se paga.
    if payload.status == "PAID":
        waiting = approvals.gate(
            db,
            membership=membership,
            user=user,
            amount=payload.amount,
            kind="EXPENSE",
            payload=payload.model_dump(mode="json"),
            summary=_expense_summary(
                db,
                org_id,
                amount=payload.amount,
                vendor_id=payload.vendor_id,
                description=payload.description,
                paying=False,
            ),
        )
        if waiting is not None:
            return JSONResponse(status_code=202, content=approvals.pending_body(db, waiting))
    expense = service.create_expense(db, org_id, payload, created_by=user.id)
    return ExpenseRead.model_validate(expense)


@router.get("/{expense_id}", response_model=ExpenseRead)
def get_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return ExpenseRead.model_validate(_get_expense(db, org_id, expense_id))


@router.post("/{expense_id}/pay", response_model=ExpenseRead)
def pay_expense(
    expense_id: str,
    payload: ExpensePay,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership=Depends(require_role(WRITE_ROLES)),
):
    expense = _get_expense(db, org_id, expense_id)
    waiting = approvals.gate(
        db,
        membership=membership,
        user=user,
        amount=expense.amount,
        kind="EXPENSE_PAYMENT",
        payload={"expense_id": expense.id, **payload.model_dump(mode="json")},
        summary=_expense_summary(
            db,
            org_id,
            amount=expense.amount,
            vendor_id=expense.vendor_id,
            description=expense.description,
            paying=True,
        ),
    )
    if waiting is not None:
        return JSONResponse(status_code=202, content=approvals.pending_body(db, waiting))
    expense = service.pay_expense(db, org_id, expense, payload.financial_account_id, payload.date, user.id)
    return ExpenseRead.model_validate(expense)


@router.post("/{expense_id}/cancel", response_model=ExpenseRead)
def cancel_expense(
    expense_id: str,
    payload: ExpenseCancel,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    expense = _get_expense(db, org_id, expense_id)
    expense = service.cancel_expense(db, expense, user.id, payload.reason)
    return ExpenseRead.model_validate(expense)


class ExpenseProjectPatch(BaseModel):
    """Lo único editable tras el registro es la etiqueta analítica. Cambiar
    montos o fechas de algo contabilizado exige reverso, nunca edición."""

    project_id: str | None


@router.patch("/{expense_id}", response_model=ExpenseRead)
def patch_expense(
    expense_id: str,
    payload: ExpenseProjectPatch,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    expense = _get_expense(db, org_id, expense_id)
    if payload.project_id is not None:
        project = (
            db.query(Project)
            .filter(Project.id == payload.project_id, Project.organization_id == org_id)
            .first()
        )
        if project is None:
            raise HTTPException(status_code=400, detail="Ese proyecto no existe en tu empresa.")
    expense.project_id = payload.project_id
    db.commit()
    db.refresh(expense)
    return ExpenseRead.model_validate(expense)
