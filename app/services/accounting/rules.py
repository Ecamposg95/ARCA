"""Motor de reglas contables (task pack §18) — centralizado.

Cada evento de negocio tiene UNA función aquí que construye su póliza.
Prohibido armar asientos en routers o en el frontend.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.services.accounting.coa import (
    CODE_ACCOUNTS_PAYABLE,
    CODE_ACCOUNTS_RECEIVABLE,
    CODE_CAPITAL,
    CODE_CASH_BANK,
    CODE_VAT_CHARGED_COLLECTED,
    CODE_VAT_CHARGED_PENDING,
    CODE_VAT_CREDITABLE_PAID,
    CODE_VAT_CREDITABLE_PENDING,
)
from app.services.accounting.engine import LineSpec, post_journal_entry


def opening_balance_entry(
    db: Session,
    organization_id: str,
    account_name: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    account_code: str = CODE_CASH_BANK,
    liability: bool = False,
) -> JournalEntry:
    """Alta de instrumento con saldo inicial.

    Activo: Cargo al instrumento / Abono Capital (aportas dinero).
    Pasivo: Cargo Capital / Abono al instrumento (arrastras una deuda).
    """
    lines = (
        [
            LineSpec(CODE_CAPITAL, debit=amount, description="Deuda inicial"),
            LineSpec(account_code, credit=amount, description=account_name),
        ]
        if liability
        else [
            LineSpec(account_code, debit=amount, description=account_name),
            LineSpec(CODE_CAPITAL, credit=amount, description="Aportación inicial"),
        ]
    )
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=f"Saldo inicial de {account_name}",
        lines=lines,
        source_type="financial_account",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def income_paid_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    revenue_account_code: str,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Ingreso cobrado: Cargo Caja y Bancos (total) / Abono Ingresos (base) + IVA trasladado."""
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(cash_account_code, debit=amount),
        LineSpec(revenue_account_code, credit=amount - tax_amount),
    ]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CHARGED_COLLECTED, credit=tax_amount, description="IVA trasladado"))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="income",
        source_id=source_id,
        created_by=created_by,
        kind="INGRESO",
    )


def expense_paid_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    expense_account_code: str,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Gasto pagado: Cargo Gastos (base) + IVA acreditable / Abono Caja y Bancos (total)."""
    tax_amount = Decimal(tax_amount)
    lines = [LineSpec(expense_account_code, debit=amount - tax_amount)]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CREDITABLE_PAID, debit=tax_amount, description="IVA acreditable"))
    lines.append(LineSpec(cash_account_code, credit=amount))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="expense",
        source_id=source_id,
        created_by=created_by,
        kind="EGRESO",
    )


def receivable_created_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    revenue_account_code: str,
    source_id: str,
    created_by: str | None = None,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """CxC emitida (devengo): Cargo CxC (total) / Abono Ingresos (base) + IVA pendiente de cobro."""
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(CODE_ACCOUNTS_RECEIVABLE, debit=amount),
        LineSpec(revenue_account_code, credit=amount - tax_amount),
    ]
    if tax_amount > 0:
        lines.append(
            LineSpec(CODE_VAT_CHARGED_PENDING, credit=tax_amount, description="IVA pendiente de cobro")
        )
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="receivable",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def receivable_collected_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Cobro de CxC: Cargo Caja y Bancos / Abono CxC.

    El IVA proporcional pasa de "pendiente de cobro" a "cobrado": es hasta
    ahora cuando se declara ante el SAT.
    """
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(cash_account_code, debit=amount),
        LineSpec(CODE_ACCOUNTS_RECEIVABLE, credit=amount),
    ]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CHARGED_PENDING, debit=tax_amount, description="IVA ahora cobrado"))
        lines.append(LineSpec(CODE_VAT_CHARGED_COLLECTED, credit=tax_amount, description="IVA trasladado"))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="receivable",
        source_id=source_id,
        created_by=created_by,
        kind="INGRESO",
    )


def payable_created_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    expense_account_code: str,
    source_id: str,
    created_by: str | None = None,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """CxP registrada (devengo): Cargo Gastos (base) + IVA pendiente / Abono CxP (total)."""
    tax_amount = Decimal(tax_amount)
    lines = [LineSpec(expense_account_code, debit=amount - tax_amount)]
    if tax_amount > 0:
        lines.append(
            LineSpec(CODE_VAT_CREDITABLE_PENDING, debit=tax_amount, description="IVA pendiente de pago")
        )
    lines.append(LineSpec(CODE_ACCOUNTS_PAYABLE, credit=amount))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="payable",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def payable_payment_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Pago de CxP: Cargo CxP / Abono Caja y Bancos.

    El IVA proporcional pasa de "pendiente de pago" a acreditable: es hasta
    ahora cuando puede acreditarse.
    """
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(CODE_ACCOUNTS_PAYABLE, debit=amount),
        LineSpec(cash_account_code, credit=amount),
    ]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CREDITABLE_PAID, debit=tax_amount, description="IVA acreditable"))
        lines.append(
            LineSpec(CODE_VAT_CREDITABLE_PENDING, credit=tax_amount, description="IVA ya pagado")
        )
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="payable",
        source_id=source_id,
        created_by=created_by,
        kind="EGRESO",
    )


def reversal_of(
    db: Session,
    organization_id: str,
    entry: JournalEntry,
    description: str,
    date: date_type,
    created_by: str | None = None,
) -> JournalEntry:
    """Asiento de reversa: las mismas líneas del original con cargo↔abono invertidos.

    Es la única forma correcta de 'deshacer' contabilidad: el original nunca
    se toca (task pack §27).
    """
    rows = (
        db.query(JournalEntryLine, Account.code)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(JournalEntryLine.journal_entry_id == entry.id)
        .all()
    )
    if not rows:
        raise ValueError("El asiento original no tiene líneas que revertir.")
    lines = [
        LineSpec(
            code,
            debit=Decimal(line.credit),
            credit=Decimal(line.debit),
            description=line.description,
        )
        for line, code in rows
    ]
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type=entry.source_type,
        source_id=entry.source_id,
        reference=f"reversal:{entry.id}",
        created_by=created_by,
        kind="DIARIO",
    )


def transfer_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    from_account_name: str,
    to_account_name: str,
    source_id: str,
    created_by: str | None = None,
    from_account_code: str = CODE_CASH_BANK,
    to_account_code: str = CODE_CASH_BANK,
) -> JournalEntry:
    """Traspaso entre instrumentos propios.

    Entre dos activos es neutro. De banco a tarjeta es un PAGO de deuda:
    Cargo 2200 (debes menos) / Abono 1100 (tienes menos). No es un gasto:
    el gasto ocurrió cuando deslizaste la tarjeta.
    """
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(to_account_code, debit=amount, description=f"Entrada a {to_account_name}"),
            LineSpec(from_account_code, credit=amount, description=f"Salida de {from_account_name}"),
        ],
        source_type="transfer",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )
