from datetime import date
from decimal import Decimal

import pytest

from app.models.accounting import JournalEntryLine
from app.models.organization import Organization
from app.services.accounting.coa import DEFAULT_CHART, seed_chart_of_accounts
from app.services.accounting.engine import (
    AccountingError,
    LineSpec,
    UnbalancedEntryError,
    post_journal_entry,
    trial_balance,
)


@pytest.fixture()
def org(db):
    organization = Organization(name="Ledger Org")
    db.add(organization)
    db.flush()
    seed_chart_of_accounts(db, organization.id)
    return organization


def test_seed_creates_full_catalog(db, org):
    rows = db.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM accounts WHERE organization_id = :o"),
        {"o": org.id},
    ).scalar()
    assert rows == len(DEFAULT_CHART)


def test_unbalanced_entry_rejected(db, org):
    with pytest.raises(UnbalancedEntryError):
        post_journal_entry(
            db,
            org.id,
            date=date(2026, 8, 1),
            description="desbalanceado",
            lines=[
                LineSpec("1100", debit=Decimal("100")),
                LineSpec("4100", credit=Decimal("90")),
            ],
        )


def test_line_with_both_debit_and_credit_rejected(db, org):
    with pytest.raises(AccountingError):
        post_journal_entry(
            db,
            org.id,
            date=date(2026, 8, 1),
            description="línea inválida",
            lines=[
                LineSpec("1100", debit=Decimal("100"), credit=Decimal("100")),
                LineSpec("4100", credit=Decimal("0")),
            ],
        )


def test_balanced_entry_persists(db, org):
    entry = post_journal_entry(
        db,
        org.id,
        date=date(2026, 8, 1),
        description="venta de mostrador",
        lines=[
            LineSpec("1100", debit=Decimal("150.50")),
            LineSpec("4100", credit=Decimal("150.50")),
        ],
        source_type="income",
        source_id="x" * 36,
    )
    lines = db.query(JournalEntryLine).filter(JournalEntryLine.journal_entry_id == entry.id).all()
    assert len(lines) == 2
    assert sum(line.debit for line in lines) == sum(line.credit for line in lines)


def test_unknown_account_code_rejected(db, org):
    with pytest.raises(ValueError, match="9999"):
        post_journal_entry(
            db,
            org.id,
            date=date(2026, 8, 1),
            description="cuenta inexistente",
            lines=[
                LineSpec("9999", debit=Decimal("10")),
                LineSpec("4100", credit=Decimal("10")),
            ],
        )


def test_cross_org_accounts_isolated(db, org):
    other = Organization(name="Otra Org")
    db.add(other)
    db.flush()
    # `other` no tiene catálogo: el motor no debe encontrar cuentas de `org`
    with pytest.raises(ValueError):
        post_journal_entry(
            db,
            other.id,
            date=date(2026, 8, 1),
            description="cruce de tenant",
            lines=[
                LineSpec("1100", debit=Decimal("10")),
                LineSpec("4100", credit=Decimal("10")),
            ],
        )


def test_receivable_and_payable_rules(db, org):
    from app.services.accounting.rules import (
        payable_created_entry,
        payable_payment_entry,
        receivable_collected_entry,
        receivable_created_entry,
    )

    receivable_created_entry(db, org.id, "Factura a crédito", Decimal("700"), date(2026, 8, 1), "4100", "r" * 36)
    receivable_collected_entry(db, org.id, "Cobro parcial", Decimal("300"), date(2026, 8, 5), "r" * 36)
    payable_created_entry(db, org.id, "Renta por pagar", Decimal("400"), date(2026, 8, 1), "5300", "p" * 36)
    payable_payment_entry(db, org.id, "Pago de renta", Decimal("400"), date(2026, 8, 10), "p" * 36)

    rows = {row["code"]: row["balance"] for row in trial_balance(db, org.id)}
    assert rows["1200"] == Decimal("400")  # CxC pendiente 700-300
    assert rows["1100"] == Decimal("-100")  # cobró 300, pagó 400
    assert rows["4100"] == Decimal("700")
    assert rows["5300"] == Decimal("400")
    assert rows["2100"] == Decimal("0")  # CxP liquidada
    total = trial_balance(db, org.id)
    assert sum(r["debit"] for r in total) == sum(r["credit"] for r in total)


def test_reversal_of_nets_to_zero(db, org):
    from app.services.accounting.rules import receivable_created_entry, reversal_of

    entry = receivable_created_entry(
        db, org.id, "Factura cancelable", Decimal("500"), date(2026, 8, 1), "4100", "x" * 36
    )
    reversal = reversal_of(db, org.id, entry, "Cancelación: Factura cancelable", date(2026, 8, 2))
    assert reversal.reference == f"reversal:{entry.id}"
    rows = {row["code"]: row["balance"] for row in trial_balance(db, org.id)}
    assert rows["1200"] == Decimal("0")
    assert rows["4100"] == Decimal("0")


def test_trial_balance_debits_equal_credits(db, org):
    post_journal_entry(
        db,
        org.id,
        date=date(2026, 8, 1),
        description="venta",
        lines=[LineSpec("1100", debit=Decimal("1000")), LineSpec("4100", credit=Decimal("1000"))],
    )
    post_journal_entry(
        db,
        org.id,
        date=date(2026, 8, 2),
        description="renta",
        lines=[LineSpec("5300", debit=Decimal("400")), LineSpec("1100", credit=Decimal("400"))],
    )
    rows = trial_balance(db, org.id)
    total_debit = sum(row["debit"] for row in rows)
    total_credit = sum(row["credit"] for row in rows)
    assert total_debit == total_credit == Decimal("1400")
