"""Reportes financieros — SIEMPRE derivados del ledger, nunca almacenados."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import Account, DEBIT_NORMAL_TYPES, JournalEntry, JournalEntryLine
from app.models.financial_account import FinancialAccount
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.services.accounting.engine import account_type_balance


def _lines_by_account(
    db: Session,
    organization_id: str,
    account_types: tuple[str, ...],
    start: date_type | None = None,
    end: date_type | None = None,
) -> list[dict]:
    query = (
        db.query(
            Account.code,
            Account.name,
            Account.type,
            func.coalesce(func.sum(JournalEntryLine.debit), 0).label("debit"),
            func.coalesce(func.sum(JournalEntryLine.credit), 0).label("credit"),
        )
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(
            Account.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            Account.type.in_(account_types),
        )
        .group_by(Account.code, Account.name, Account.type)
        .order_by(Account.code)
    )
    if start is not None:
        query = query.filter(JournalEntry.date >= start)
    if end is not None:
        query = query.filter(JournalEntry.date <= end)

    rows = []
    for code, name, account_type, debit, credit in query.all():
        debit = Decimal(debit or 0)
        credit = Decimal(credit or 0)
        balance = debit - credit if account_type in DEBIT_NORMAL_TYPES else credit - debit
        if balance == 0:
            continue
        rows.append({"code": code, "name": name, "type": account_type, "amount": balance})
    return rows


def profit_loss(db: Session, organization_id: str, start: date_type, end: date_type) -> dict:
    revenue_lines = _lines_by_account(db, organization_id, ("REVENUE",), start, end)
    expense_lines = _lines_by_account(db, organization_id, ("EXPENSE",), start, end)
    total_revenue = sum((row["amount"] for row in revenue_lines), Decimal("0"))
    total_expenses = sum((row["amount"] for row in expense_lines), Decimal("0"))
    return {
        "start": start,
        "end": end,
        "revenue": revenue_lines,
        "expenses": expense_lines,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_profit": total_revenue - total_expenses,
    }


def balance_sheet(db: Session, organization_id: str, as_of: date_type) -> dict:
    assets = _lines_by_account(db, organization_id, ("ASSET",), end=as_of)
    liabilities = _lines_by_account(db, organization_id, ("LIABILITY",), end=as_of)
    equity = _lines_by_account(db, organization_id, ("EQUITY",), end=as_of)

    total_assets = sum((row["amount"] for row in assets), Decimal("0"))
    total_liabilities = sum((row["amount"] for row in liabilities), Decimal("0"))
    total_equity_accounts = sum((row["amount"] for row in equity), Decimal("0"))

    # Resultado del ejercicio (ingresos - gastos) vive en capital hasta el cierre.
    revenue = account_type_balance(db, organization_id, "REVENUE", end=as_of)
    expenses = account_type_balance(db, organization_id, "EXPENSE", end=as_of)
    period_result = revenue - expenses
    if period_result != 0:
        equity = [*equity, {"code": "3999", "name": "Resultado del periodo", "type": "EQUITY", "amount": period_result}]
    total_equity = total_equity_accounts + period_result

    return {
        "as_of": as_of,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "balanced": total_assets == total_liabilities + total_equity,
    }


def cash_flow(db: Session, organization_id: str, start: date_type, end: date_type) -> dict:
    def _flows(until: date_type | None, since: date_type | None) -> tuple[Decimal, Decimal]:
        query = db.query(
            FinancialTransaction.transaction_type,
            func.coalesce(func.sum(FinancialTransaction.amount), 0),
        ).filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.status == "ACTIVE",
        )
        if since is not None:
            query = query.filter(FinancialTransaction.date >= since)
        if until is not None:
            query = query.filter(FinancialTransaction.date <= until)
        inflows = Decimal("0")
        outflows = Decimal("0")
        for transaction_type, amount in query.group_by(FinancialTransaction.transaction_type).all():
            if transaction_type in INFLOW_TYPES:
                inflows += Decimal(amount or 0)
            else:
                outflows += Decimal(amount or 0)
        return inflows, outflows

    opening_from_accounts = (
        db.query(func.coalesce(func.sum(FinancialAccount.opening_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .scalar()
    )
    inflows_before, outflows_before = _flows(until=None, since=None)
    # opening = saldos iniciales + neto de movimientos ANTERIORES al periodo
    inflows_pre, outflows_pre = _flows(until=None, since=start)
    net_before_period = (inflows_before - outflows_before) - (inflows_pre - outflows_pre)
    opening_cash = Decimal(opening_from_accounts or 0) + net_before_period

    inflows, outflows = _flows(until=end, since=start)
    return {
        "start": start,
        "end": end,
        "opening_cash": opening_cash,
        "inflows": inflows,
        "outflows": outflows,
        "closing_cash": opening_cash + inflows - outflows,
    }


def vat_report(db: Session, organization_id: str, start: date_type, end: date_type) -> dict:
    """IVA del periodo por flujo de efectivo: sólo lo cobrado y lo pagado se declara."""
    from app.services.accounting.coa import (
        CODE_VAT_CHARGED_COLLECTED,
        CODE_VAT_CHARGED_PENDING,
        CODE_VAT_CREDITABLE_PAID,
        CODE_VAT_CREDITABLE_PENDING,
    )

    def movement(code: str, since: date_type | None, until: date_type) -> Decimal:
        """Saldo neto de una cuenta de IVA en el periodo (naturaleza de la cuenta)."""
        query = (
            db.query(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalEntry.status == "POSTED",
                Account.code == code,
                JournalEntry.date <= until,
            )
        )
        if since is not None:
            query = query.filter(JournalEntry.date >= since)
        debit, credit = query.one()
        debit, credit = Decimal(debit or 0), Decimal(credit or 0)
        # 2190/2191 son pasivo (naturaleza acreedora); 1190/1191 activo (deudora).
        return credit - debit if code.startswith("2") else debit - credit

    charged = movement(CODE_VAT_CHARGED_COLLECTED, start, end)
    creditable = movement(CODE_VAT_CREDITABLE_PAID, start, end)
    difference = charged - creditable

    return {
        "start": start,
        "end": end,
        "vat_charged": charged,
        "vat_creditable": creditable,
        "difference": difference,
        "to_pay": difference if difference > 0 else Decimal("0"),
        "in_favor": -difference if difference < 0 else Decimal("0"),
        # Informativos: aún no se declaran porque no se han cobrado/pagado.
        "vat_pending_collection": movement(CODE_VAT_CHARGED_PENDING, None, end),
        "vat_pending_payment": movement(CODE_VAT_CREDITABLE_PENDING, None, end),
    }


def cash_projection(db: Session, organization_id: str, days: int = 90) -> dict:
    """Proyección de liquidez con lo YA comprometido: no es un pronóstico.

    Parte del efectivo de hoy y camina hacia adelante sumando los cobros
    esperados y restando los pagos comprometidos en su fecha de vencimiento.
    Lo vencido se considera exigible de inmediato.
    """
    from datetime import timedelta

    from app.models.financial_account import ASSET_ACCOUNT_TYPES, FinancialAccount
    from app.models.payable import Payable
    from app.models.receivable import Receivable

    today = date_type.today()
    horizon = today + timedelta(days=days)

    opening = Decimal(
        db.query(func.coalesce(func.sum(FinancialAccount.current_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.type.in_(ASSET_ACCOUNT_TYPES),
        )
        .scalar()
        or 0
    )

    def pending(model, sign: int) -> list[tuple[date_type, Decimal, str]]:
        rows = (
            db.query(model.due_date, model.amount, model.amount_paid, model.description)
            .filter(
                model.organization_id == organization_id,
                model.status.in_(("OPEN", "PARTIAL")),
                model.due_date <= horizon,
            )
            .all()
        )
        items = []
        for due_date, amount, paid, description in rows:
            balance = Decimal(amount) - Decimal(paid)
            if balance <= 0:
                continue
            # Lo vencido ya es exigible: se coloca en el día de hoy.
            when = max(due_date, today)
            items.append((when, balance * sign, description))
        return items

    movements = pending(Receivable, 1) + pending(Payable, -1)
    movements.sort(key=lambda item: item[0])

    balance = opening
    points: list[dict] = [{"date": today, "balance": balance, "change": Decimal("0")}]
    shortfall: date_type | None = None
    inflows = Decimal("0")
    outflows = Decimal("0")

    for when, change, _description in movements:
        balance += change
        if change > 0:
            inflows += change
        else:
            outflows += -change
        if shortfall is None and balance < 0:
            shortfall = when
        points.append({"date": when, "balance": balance, "change": change})

    return {
        "start": today,
        "end": horizon,
        "opening_cash": opening,
        "expected_inflows": inflows,
        "expected_outflows": outflows,
        "projected_cash": balance,
        # El día en que el dinero no alcanza: la alerta que nadie más da.
        "shortfall_date": shortfall,
        "points": points,
    }
