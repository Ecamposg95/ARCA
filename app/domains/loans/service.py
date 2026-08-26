"""Préstamos: alta, tabla de amortización y pagos que separan capital de interés.

Todo el módulo existe por una sola razón contable: el pago de un crédito no es
gasto. La parte que reduce la deuda no toca el resultado; sólo el interés sí.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.loan import Loan, LoanPayment
from app.services.accounting.engine import _quantize
from app.services.accounting.rules import loan_payment_entry, loan_received_entry
from app.services.transactions import account_ledger_code, record_transaction


def monthly_rate(annual_rate: Decimal) -> Decimal:
    return Decimal(annual_rate) / Decimal("12")


def monthly_payment(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """Pago fijo del sistema francés. Sin tasa, es simplemente el capital entre plazos."""
    principal = Decimal(principal)
    rate = monthly_rate(annual_rate)
    if term_months <= 0:
        raise ValueError("El plazo debe ser de al menos un mes.")
    if rate == 0:
        return _quantize(principal / Decimal(term_months))
    factor = (Decimal("1") + rate) ** term_months
    return _quantize(principal * rate * factor / (factor - Decimal("1")))


def amortization_schedule(
    principal: Decimal, annual_rate: Decimal, term_months: int, start_date: date_type
) -> list[dict]:
    """Tabla completa: cuánto de cada pago es interés y cuánto baja la deuda.

    La última cuota absorbe el redondeo para que el saldo termine exactamente en
    cero; de otro modo quedarían centavos de deuda fantasma.
    """
    payment = monthly_payment(principal, annual_rate, term_months)
    rate = monthly_rate(annual_rate)
    balance = _quantize(Decimal(principal))
    rows: list[dict] = []

    for number in range(1, term_months + 1):
        interest = _quantize(balance * rate)
        capital = payment - interest
        if number == term_months or capital >= balance:
            capital = balance
            payment_now = capital + interest
        else:
            payment_now = payment
        balance = _quantize(balance - capital)
        index = start_date.year * 12 + (start_date.month - 1) + number
        year, month = divmod(index, 12)
        rows.append(
            {
                "number": number,
                "due_date": date_type(year, month + 1, min(start_date.day, 28)),
                "payment": payment_now,
                "principal": capital,
                "interest": interest,
                "balance": balance,
            }
        )
        if balance <= 0:
            break
    return rows


def create_loan(
    db: Session,
    organization_id: str,
    *,
    lender: str,
    description: str,
    principal: Decimal,
    annual_rate: Decimal,
    term_months: int,
    start_date: date_type,
    financial_account_id: str | None = None,
    payment_day: int = 1,
    notes: str | None = None,
    user_id: str | None = None,
) -> Loan:
    principal = _quantize(Decimal(principal))

    loan = Loan(
        organization_id=organization_id,
        lender=lender,
        description=description,
        principal=principal,
        outstanding=principal,
        annual_rate=Decimal(annual_rate),
        term_months=term_months,
        start_date=start_date,
        payment_day=payment_day,
        financial_account_id=financial_account_id,
        notes=notes,
        created_by=user_id,
    )
    db.add(loan)
    db.flush()

    # Si el dinero entró a una cuenta, se registra la entrada y nace la deuda.
    if financial_account_id:
        record_transaction(
            db,
            organization_id=organization_id,
            financial_account_id=financial_account_id,
            transaction_type="INCOME",
            amount=principal,
            date=start_date,
            description=f"Préstamo recibido: {lender}",
            source_type="loan",
            source_id=loan.id,
            created_by=user_id,
        )
        loan_received_entry(
            db,
            organization_id,
            description=f"Préstamo recibido: {lender}",
            amount=principal,
            date=start_date,
            source_id=loan.id,
            created_by=user_id,
            cash_account_code=account_ledger_code(db, organization_id, financial_account_id),
        )

    db.commit()
    db.refresh(loan)
    return loan


def register_payment(
    db: Session,
    organization_id: str,
    loan: Loan,
    *,
    amount: Decimal,
    financial_account_id: str,
    date: date_type,
    user_id: str | None = None,
) -> LoanPayment:
    """Registra un pago partiéndolo en interés del periodo y capital.

    El interés se calcula sobre el saldo vigente, así que pagar de más adelanta
    capital y pagar de menos no lo permite si no cubre ni el interés.
    """
    amount = _quantize(Decimal(amount))
    outstanding = Decimal(loan.outstanding)

    if loan.status != "ACTIVE":
        raise ValueError("Este préstamo ya no está vigente.")

    interest = _quantize(outstanding * monthly_rate(loan.annual_rate))
    if amount <= interest and outstanding > 0 and interest > 0:
        raise ValueError(
            f"El pago no alcanza a cubrir los intereses del periodo (${interest}). "
            "La deuda no bajaría."
        )

    capital = amount - interest
    if capital > outstanding:
        # Liquidación: no se puede abonar más capital del que se debe.
        capital = outstanding
        amount = capital + interest

    payment = LoanPayment(
        organization_id=organization_id,
        loan_id=loan.id,
        date=date,
        amount=amount,
        principal_part=capital,
        interest_part=interest,
        financial_account_id=financial_account_id,
        created_by=user_id,
    )
    db.add(payment)
    db.flush()

    record_transaction(
        db,
        organization_id=organization_id,
        financial_account_id=financial_account_id,
        transaction_type="EXPENSE",
        amount=amount,
        date=date,
        description=f"Pago de préstamo: {loan.lender}",
        source_type="loan_payment",
        source_id=payment.id,
        created_by=user_id,
    )
    loan_payment_entry(
        db,
        organization_id,
        description=f"Pago de préstamo: {loan.lender}",
        principal=capital,
        interest=interest,
        date=date,
        source_id=payment.id,
        created_by=user_id,
        cash_account_code=account_ledger_code(db, organization_id, financial_account_id),
    )

    loan.outstanding = _quantize(outstanding - capital)
    if loan.outstanding <= 0:
        loan.status = "PAID"

    db.commit()
    db.refresh(payment)
    return payment


def cancel_loan(db: Session, loan: Loan) -> Loan:
    loan.status = "CANCELLED"
    loan.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(loan)
    return loan


def summary(db: Session, organization_id: str) -> dict:
    loans = (
        db.query(Loan)
        .filter(Loan.organization_id == organization_id, Loan.status == "ACTIVE")
        .all()
    )
    outstanding = sum((Decimal(loan.outstanding) for loan in loans), Decimal("0"))
    next_payments = sum(
        (monthly_payment(loan.principal, loan.annual_rate, loan.term_months) for loan in loans),
        Decimal("0"),
    )
    return {
        "count": len(loans),
        "outstanding": outstanding,
        "monthly_commitment": next_payments,
    }
