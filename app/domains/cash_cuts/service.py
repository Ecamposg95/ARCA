"""Corte de caja: esperado vs contado, diferencia explicada y entrega.

El corte no escribe al libro por su cuenta. La diferencia es un ingreso o un
gasto "Diferencias de caja" pagado en esa caja (para que su saldo quede en lo
contado) y la entrega es un traspaso caja → caja central o banco. Deshacer
cualquiera de los dos es revertir, nunca borrar.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domains.expenses.schemas import ExpenseCreate
from app.domains.expenses.service import cancel_expense, create_expense
from app.domains.income.schemas import IncomeCreate
from app.domains.income.service import cancel_income, create_income
from app.domains.transactions.service import create_transfer, reverse_transfer
from app.models.cash_cut import CashCut
from app.models.category import Category
from app.models.expense import Expense
from app.models.financial_account import FinancialAccount
from app.models.income import Income
from app.models.organization import ROLE_ADMIN, ROLE_OWNER
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.services.accounting.coa import CODE_OTHER_EXPENSES, CODE_SALES
from app.services.accounting.engine import _quantize
from app.services.categories import ensure_system_category

# La diferencia del arqueo: faltante es gasto, sobrante es ingreso. Comparten
# nombre porque para el empresario son lo mismo visto de dos lados.
DIFFERENCE_CATEGORY = "Diferencias de caja"
SHORTAGE_CATEGORY = (DIFFERENCE_CATEGORY, "EXPENSE", CODE_OTHER_EXPENSES)
SURPLUS_CATEGORY = (DIFFERENCE_CATEGORY, "INCOME", CODE_SALES)

# Cortes que cuentan para "uno por caja y día" y para el resumen de hoy.
LIVE_STATUSES = ("OPEN", "COUNTED", "DELIVERED")
# Quien entrega no confirma su propia entrega, salvo que administre la empresa.
SELF_CONFIRM_ROLES = (ROLE_OWNER, ROLE_ADMIN)


class CashCutConflictError(ValueError):
    """Ya hay un corte vigente de esa caja ese día (409)."""


class CashCutForbiddenError(PermissionError):
    """La acción no le toca a este usuario (403)."""


def get_cash_account(db: Session, organization_id: str, account_id: str) -> FinancialAccount:
    account = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == account_id,
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if account is None:
        raise LookupError("La caja no existe.")
    if account.type != "CASH":
        raise ValueError("El corte es de una caja de efectivo.")
    if not account.active:
        raise ValueError("Esa caja está inactiva.")
    return account


def get_cut(db: Session, organization_id: str, cut_id: str) -> CashCut:
    cut = db.query(CashCut).filter(CashCut.id == cut_id, CashCut.organization_id == organization_id).first()
    if cut is None:
        raise LookupError("El corte no existe.")
    return cut


def _cut_operation_ids(db: Session, organization_id: str, account_id: str, day: date_type):
    """Ids de las operaciones que nacen de un corte en esa caja: los ingresos y
    gastos "Diferencias de caja" y los traspasos de entrega de ese día.

    Sus movimientos (y los reversos de esos movimientos) no son del día: son
    el resultado del arqueo, y contarlos haría que el esperado persiga al
    contado. Se excluyen de entradas y salidas.
    """
    category_ids = db.query(Category.id).filter(
        Category.organization_id == organization_id, Category.name == DIFFERENCE_CATEGORY
    )
    expenses = db.query(Expense.id).filter(
        Expense.organization_id == organization_id,
        Expense.financial_account_id == account_id,
        Expense.category_id.in_(category_ids),
    )
    incomes = db.query(Income.id).filter(
        Income.organization_id == organization_id,
        Income.financial_account_id == account_id,
        Income.category_id.in_(category_ids),
    )
    deliveries = db.query(CashCut.transfer_group_id).filter(
        CashCut.organization_id == organization_id,
        CashCut.financial_account_id == account_id,
        CashCut.date == day,
        CashCut.transfer_group_id.isnot(None),
    )
    return expenses, incomes, deliveries


def day_flows(db: Session, organization_id: str, account: FinancialAccount, day: date_type) -> dict:
    """Apertura, entradas, salidas y esperado de la caja ese día.

    La apertura se desanda desde el saldo actual (la cifra que el usuario ve)
    quitando todo lo que pasó desde ese día, ajustes incluidos; así cuadra
    aunque la caja haya nacido con saldo inicial sin movimiento. Las entradas
    y salidas del día no cuentan los ajustes de arqueo.
    """
    expenses, incomes, deliveries = _cut_operation_ids(db, organization_id, account.id, day)
    base = db.query(
        FinancialTransaction.transaction_type,
        func.coalesce(func.sum(FinancialTransaction.amount), 0),
    ).filter(
        FinancialTransaction.organization_id == organization_id,
        FinancialTransaction.financial_account_id == account.id,
        FinancialTransaction.status == "ACTIVE",
    )

    def sums(query) -> tuple[Decimal, Decimal]:
        inflow = outflow = Decimal("0")
        for tx_type, amount in query.group_by(FinancialTransaction.transaction_type).all():
            if tx_type in INFLOW_TYPES:
                inflow += Decimal(amount or 0)
            else:
                outflow += Decimal(amount or 0)
        return inflow, outflow

    since_in, since_out = sums(base.filter(FinancialTransaction.date >= day))
    day_in, day_out = sums(
        base.filter(
            FinancialTransaction.date == day,
            or_(FinancialTransaction.source_id.is_(None), FinancialTransaction.source_id.notin_(expenses)),
            or_(FinancialTransaction.source_id.is_(None), FinancialTransaction.source_id.notin_(incomes)),
            or_(FinancialTransaction.source_id.is_(None), FinancialTransaction.source_id.notin_(deliveries)),
        )
    )
    opening = Decimal(account.current_balance) - since_in + since_out
    return {
        "opening_balance": opening,
        "inflows": day_in,
        "outflows": day_out,
        "expected_closing": opening + day_in - day_out,
    }


def _live_cut(db: Session, organization_id: str, account_id: str, day: date_type) -> CashCut | None:
    return (
        db.query(CashCut)
        .filter(
            CashCut.organization_id == organization_id,
            CashCut.financial_account_id == account_id,
            CashCut.date == day,
            CashCut.status.in_(LIVE_STATUSES),
        )
        .first()
    )


def create_cut(db: Session, organization_id: str, account_id: str, day: date_type, user_id: str) -> CashCut:
    """Abre el corte del día con lo que debería haber en la caja. No hace commit."""
    account = get_cash_account(db, organization_id, account_id)
    if day > date_type.today():
        raise ValueError("El corte es de hoy o de un día que ya pasó.")
    if _live_cut(db, organization_id, account.id, day) is not None:
        raise CashCutConflictError("Esa caja ya tiene corte de ese día.")
    cut = CashCut(
        organization_id=organization_id,
        financial_account_id=account.id,
        business_unit_id=account.business_unit_id,
        date=day,
        status="OPEN",
        created_by=user_id,
        **day_flows(db, organization_id, account, day),
    )
    db.add(cut)
    db.flush()
    return cut


def _revert_adjustment(db: Session, organization_id: str, cut: CashCut, user_id: str) -> None:
    if not cut.adjustment_transaction_id:
        return
    movement = db.get(FinancialTransaction, cut.adjustment_transaction_id)
    if movement is not None and movement.organization_id == organization_id:
        if movement.source_type == "expense":
            expense = db.get(Expense, movement.source_id)
            cancel_expense(db, expense, user_id, "Recuento de caja", commit=False, reversal_date=cut.date)
        elif movement.source_type == "income":
            income = db.get(Income, movement.source_id)
            cancel_income(db, income, user_id, "Recuento de caja", commit=False, reversal_date=cut.date)
    cut.adjustment_transaction_id = None


def _record_adjustment(
    db: Session, organization_id: str, cut: CashCut, account: FinancialAccount, difference: Decimal, user_id: str
) -> str:
    """Ingreso (sobrante) o gasto (faltante) en la caja, fechado el día del corte."""
    label = f"Diferencia de caja {account.name} {cut.date.isoformat()}"
    if difference < 0:
        category = ensure_system_category(db, organization_id, *SHORTAGE_CATEGORY)
        operation = create_expense(
            db,
            organization_id,
            ExpenseCreate(
                date=cut.date,
                description=f"Faltante · {label}",
                amount=-difference,
                category_id=category.id,
                financial_account_id=account.id,
                status="PAID",
                notes=cut.explanation,
            ),
            created_by=user_id,
            commit=False,
        )
        source_type = "expense"
    else:
        category = ensure_system_category(db, organization_id, *SURPLUS_CATEGORY)
        operation = create_income(
            db,
            organization_id,
            IncomeCreate(
                date=cut.date,
                description=f"Sobrante · {label}",
                amount=difference,
                category_id=category.id,
                financial_account_id=account.id,
                status="PAID",
                notes=cut.explanation,
            ),
            created_by=user_id,
            commit=False,
        )
        source_type = "income"
    movement = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.source_type == source_type,
            FinancialTransaction.source_id == operation.id,
        )
        .one()
    )
    return movement.id


def count_cut(
    db: Session,
    organization_id: str,
    cut: CashCut,
    counted_amount: Decimal,
    explanation: str | None,
    user_id: str,
) -> CashCut:
    """Fija contado y diferencia; si hay diferencia, la registra en la caja.

    Un corte ya contado se puede recontar: se revierte el ajuste anterior y
    se registra el nuevo. No hace commit.
    """
    if cut.status not in ("OPEN", "COUNTED"):
        raise ValueError("Este corte ya se entregó; para corregirlo, cancélalo.")
    account = get_cash_account(db, organization_id, cut.financial_account_id)
    counted = _quantize(counted_amount)
    explanation = (explanation or "").strip() or None

    _revert_adjustment(db, organization_id, cut, user_id)
    # El esperado se recalcula por si entró una venta después de abrir el corte.
    for field, value in day_flows(db, organization_id, account, cut.date).items():
        setattr(cut, field, value)
    difference = counted - Decimal(cut.expected_closing)
    if difference != 0 and not explanation:
        raise ValueError("Explica la diferencia.")

    cut.counted_amount = counted
    cut.difference = difference
    cut.explanation = explanation
    if difference != 0:
        cut.adjustment_transaction_id = _record_adjustment(db, organization_id, cut, account, difference, user_id)
    cut.status = "COUNTED"
    db.flush()
    return cut


def deliver_cut(
    db: Session,
    organization_id: str,
    cut: CashCut,
    delivered_amount: Decimal,
    to_account_id: str,
    user_id: str,
) -> CashCut:
    """Traspaso caja → caja central o banco por lo entregado. No hace commit."""
    if cut.status != "COUNTED":
        raise ValueError("Primero cuenta la caja; luego entregas.")
    amount = _quantize(delivered_amount)
    if amount > Decimal(cut.counted_amount):
        raise ValueError("No puedes entregar más de lo contado.")
    destination = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == to_account_id,
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if destination is None or not destination.active:
        raise ValueError("El destino de la entrega no existe.")
    if destination.type not in ("CASH", "BANK"):
        raise ValueError("El efectivo se entrega a una caja o a un banco.")
    account = get_cash_account(db, organization_id, cut.financial_account_id)
    transfer = create_transfer(
        db,
        organization_id,
        from_account_id=account.id,
        to_account_id=destination.id,
        amount=amount,
        date=cut.date,
        description=f"Entrega de corte {account.name} {cut.date.isoformat()}",
        user_id=user_id,
    )
    now = datetime.now(timezone.utc)
    cut.delivered_amount = amount
    cut.delivered_to_account_id = destination.id
    cut.delivered_by = user_id
    cut.delivered_at = now
    cut.transfer_group_id = transfer.group_id
    cut.status = "DELIVERED"
    cut.closed_by = user_id
    cut.closed_at = now
    db.flush()
    return cut


def confirm_receipt(db: Session, organization_id: str, cut: CashCut, user_id: str, role: str) -> CashCut:
    if cut.status != "DELIVERED":
        raise ValueError("Todavía no se entrega este corte.")
    if cut.received_by:
        raise ValueError("Esta entrega ya está confirmada.")
    if user_id == cut.delivered_by and role not in SELF_CONFIRM_ROLES:
        raise CashCutForbiddenError("Quien entrega no confirma su propia entrega.")
    cut.received_by = user_id
    cut.received_at = datetime.now(timezone.utc)
    db.flush()
    return cut


def cancel_cut(db: Session, organization_id: str, cut: CashCut, user_id: str) -> CashCut:
    """Revierte entrega y ajuste (si los hay) y deja el corte CANCELLED. No hace commit."""
    if cut.status == "CANCELLED":
        raise ValueError("Este corte ya está cancelado.")
    if cut.transfer_group_id:
        reverse_transfer(
            db,
            organization_id,
            cut.transfer_group_id,
            description=f"Reverso: entrega de corte {cut.date.isoformat()}",
            date=cut.date,
            user_id=user_id,
        )
    _revert_adjustment(db, organization_id, cut, user_id)
    cut.status = "CANCELLED"
    cut.cancelled_at = datetime.now(timezone.utc)
    cut.cancelled_by = user_id
    db.flush()
    return cut


def cuts_query(
    db: Session,
    organization_id: str,
    *,
    account_id: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    status: str | None = None,
    business_unit_id: str | None = None,
):
    query = db.query(CashCut).filter(CashCut.organization_id == organization_id)
    if account_id:
        query = query.filter(CashCut.financial_account_id == account_id)
    if date_from:
        query = query.filter(CashCut.date >= date_from)
    if date_to:
        query = query.filter(CashCut.date <= date_to)
    if status:
        query = query.filter(CashCut.status == status)
    if business_unit_id:
        query = query.filter(CashCut.business_unit_id == business_unit_id)
    return query.order_by(CashCut.date.desc(), CashCut.created_at.desc())


def today_overview(db: Session, organization_id: str) -> list[dict]:
    """Cada caja de efectivo activa con su saldo y el corte de hoy, si existe."""
    today = date_type.today()
    accounts = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.type == "CASH",
            FinancialAccount.active.is_(True),
            FinancialAccount.deleted_at.is_(None),
        )
        .order_by(FinancialAccount.created_at)
        .all()
    )
    cuts = {
        cut.financial_account_id: cut
        for cut in db.query(CashCut)
        .filter(
            CashCut.organization_id == organization_id,
            CashCut.date == today,
            CashCut.status.in_(LIVE_STATUSES),
        )
        .all()
    }
    return [
        {
            "account_id": account.id,
            "account_name": account.name,
            "business_unit_id": account.business_unit_id,
            "business_unit_name": account.business_unit_name,
            "current_balance": Decimal(account.current_balance),
            "cut": cuts.get(account.id),
        }
        for account in accounts
    ]
