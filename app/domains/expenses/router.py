from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.expenses import service
from app.domains.expenses.schemas import ExpenseCancel, ExpenseCreate, ExpensePay, ExpenseRead
from app.models.expense import Expense
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _get_expense(db: Session, org_id: str, expense_id: str) -> Expense:
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.organization_id == org_id)
        .first()
    )
    if expense is None:
        raise HTTPException(status_code=404, detail="El gasto no existe.")
    return expense


@router.get("")
def list_expenses(
    status: str | None = Query(default=None, pattern="^(PENDING|PAID|CANCELLED)$"),
    start: date_type | None = None,
    end: date_type | None = None,
    q: str | None = Query(default=None, max_length=200),
    category_id: str | None = None,
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(Expense).filter(Expense.organization_id == org_id)
    if status:
        query = query.filter(Expense.status == status)
    if start:
        query = query.filter(Expense.date >= start)
    if end:
        query = query.filter(Expense.date <= end)
    if q:
        # Búsqueda simple sobre el concepto: es como la gente recuerda una operación.
        query = query.filter(Expense.description.ilike(f"%{q}%"))
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if project_id:
        query = query.filter(Expense.project_id == project_id)
    query = query.order_by(Expense.date.desc(), Expense.created_at.desc())
    return paginate(query, limit, offset, ExpenseRead, sum_column=Expense.amount)


@router.post("", response_model=ExpenseRead, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
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
    _membership=Depends(require_role(WRITE_ROLES)),
):
    expense = _get_expense(db, org_id, expense_id)
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
