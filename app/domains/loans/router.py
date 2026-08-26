from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.loans import service
from app.domains.loans.schemas import LoanCreate, LoanPaymentCreate, LoanPaymentRead, LoanRead
from app.models.loan import Loan, LoanPayment
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/loans", tags=["loans"])


def _read(loan: Loan) -> dict:
    return {
        **{c.name: getattr(loan, c.name) for c in loan.__table__.columns},
        "monthly_payment": service.monthly_payment(
            loan.principal, loan.annual_rate, loan.term_months
        ),
        "paid_principal": Decimal(loan.principal) - Decimal(loan.outstanding),
    }


def _get_loan(db: Session, org_id: str, loan_id: str) -> Loan:
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.organization_id == org_id).first()
    if loan is None:
        raise HTTPException(status_code=404, detail="El préstamo no existe.")
    return loan


@router.get("")
def list_loans(
    status: str | None = Query(default=None, pattern="^(ACTIVE|PAID|CANCELLED)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(Loan).filter(Loan.organization_id == org_id)
    if status:
        query = query.filter(Loan.status == status)
    total = query.count()
    rows = query.order_by(Loan.start_date.desc()).limit(limit).offset(offset).all()
    return {
        "items": [_read(loan) for loan in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.summary(db, org_id)


@router.post("", response_model=LoanRead, status_code=201)
def create_loan(
    payload: LoanCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    try:
        loan = service.create_loan(
            db,
            org_id,
            lender=payload.lender,
            description=payload.description,
            principal=payload.principal,
            annual_rate=payload.annual_rate,
            term_months=payload.term_months,
            start_date=payload.start_date,
            financial_account_id=payload.financial_account_id,
            payment_day=payload.payment_day,
            notes=payload.notes,
            user_id=user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _read(loan)


@router.get("/{loan_id}/schedule")
def schedule(
    loan_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    loan = _get_loan(db, org_id, loan_id)
    return {
        "loan_id": loan.id,
        "monthly_payment": service.monthly_payment(
            loan.principal, loan.annual_rate, loan.term_months
        ),
        "rows": service.amortization_schedule(
            loan.principal, loan.annual_rate, loan.term_months, loan.start_date
        ),
    }


@router.get("/{loan_id}/payments")
def payments(
    loan_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    _get_loan(db, org_id, loan_id)
    rows = (
        db.query(LoanPayment)
        .filter(LoanPayment.organization_id == org_id, LoanPayment.loan_id == loan_id)
        .order_by(LoanPayment.date.desc())
        .all()
    )
    items = [LoanPaymentRead.model_validate(row) for row in rows]
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("/{loan_id}/pay", response_model=LoanPaymentRead, status_code=201)
def pay(
    loan_id: str,
    payload: LoanPaymentCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    loan = _get_loan(db, org_id, loan_id)
    try:
        return service.register_payment(
            db,
            org_id,
            loan,
            amount=payload.amount,
            financial_account_id=payload.financial_account_id,
            date=payload.date or date.today(),
            user_id=user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
