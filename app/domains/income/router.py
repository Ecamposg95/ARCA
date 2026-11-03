from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.income import service
from app.domains.income.listing import filter_incomes, income_export_rows
from app.domains.income.schemas import IncomeCancel, IncomeCreate, IncomePay, IncomeRead
from app.models.income import Income
from app.models.organization import WRITE_ROLES
from app.models.project import Project
from app.models.user import User
from app.schemas.common import apply_sort, paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services.listing import (
    OperationFilters,
    check_export_size,
    export_response,
    money_total_row,
    operation_filters,
)

router = APIRouter(prefix="/income", tags=["income"])


def _get_income(db: Session, org_id: str, income_id: str) -> Income:
    income = (
        db.query(Income)
        .filter(Income.id == income_id, Income.organization_id == org_id)
        .first()
    )
    if income is None:
        raise HTTPException(status_code=404, detail="El ingreso no existe.")
    return income


def _sorted(query, sort: str | None):
    return apply_sort(
        query,
        sort,
        {"date": Income.date, "amount": Income.amount},
        (Income.date.desc(), Income.created_at.desc()),
    )


@router.get("")
def list_income(
    filters: OperationFilters = Depends(operation_filters),
    sort: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = _sorted(filter_incomes(db, org_id, filters), sort)
    return paginate(query, limit, offset, IncomeRead, sum_column=Income.amount)


@router.get("/export")
def export_income(
    filters: OperationFilters = Depends(operation_filters),
    sort: str | None = Query(default=None, max_length=30),
    file_format: str = Query(default="xlsx", alias="format", pattern="^(xlsx|csv)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Los ingresos de la lista, con los mismos filtros, en Excel o CSV."""
    query = _sorted(filter_incomes(db, org_id, filters), sort)
    check_export_size(query)
    rows = income_export_rows(db, org_id, query)
    return export_response(
        rows=rows,
        total_row=money_total_row(rows),
        file_format=file_format,
        prefix="ingresos",
        sheet_title="Ingresos",
        start=filters.start,
        end=filters.end,
    )


@router.post("", response_model=IncomeRead, status_code=201)
def create_income(
    payload: IncomeCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = service.create_income(db, org_id, payload, created_by=user.id)
    return IncomeRead.model_validate(income)


@router.get("/{income_id}", response_model=IncomeRead)
def get_income(
    income_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return IncomeRead.model_validate(_get_income(db, org_id, income_id))


@router.post("/{income_id}/pay", response_model=IncomeRead)
def pay_income(
    income_id: str,
    payload: IncomePay,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = _get_income(db, org_id, income_id)
    income = service.pay_income(
        db, org_id, income, payload.financial_account_id, payload.date, user.id, payment_method=payload.payment_method
    )
    return IncomeRead.model_validate(income)


@router.post("/{income_id}/cancel", response_model=IncomeRead)
def cancel_income(
    income_id: str,
    payload: IncomeCancel,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = _get_income(db, org_id, income_id)
    income = service.cancel_income(db, income, user.id, payload.reason)
    return IncomeRead.model_validate(income)


class IncomeProjectPatch(BaseModel):
    """Lo único editable tras el registro es la etiqueta analítica. Cambiar
    montos o fechas de algo contabilizado exige reverso, nunca edición."""

    project_id: str | None


@router.patch("/{income_id}", response_model=IncomeRead)
def patch_income(
    income_id: str,
    payload: IncomeProjectPatch,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = _get_income(db, org_id, income_id)
    if payload.project_id is not None:
        project = (
            db.query(Project)
            .filter(Project.id == payload.project_id, Project.organization_id == org_id)
            .first()
        )
        if project is None:
            raise HTTPException(status_code=400, detail="Ese proyecto no existe en tu empresa.")
    income.project_id = payload.project_id
    db.commit()
    db.refresh(income)
    return IncomeRead.model_validate(income)
