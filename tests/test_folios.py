"""Folios de póliza: series independientes por organización, tipo y mes."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.organization import Organization
from app.services.accounting.coa import seed_chart_of_accounts
from app.services.accounting.engine import LineSpec, post_journal_entry
from app.services.accounting.rules import (
    expense_paid_entry,
    income_paid_entry,
    receivable_created_entry,
    reversal_of,
)


@pytest.fixture()
def org(db):
    organization = Organization(name="Folios SA")
    db.add(organization)
    db.flush()
    seed_chart_of_accounts(db, organization.id)
    return organization


def _post(db, org_id, kind="DIARIO", when=date(2026, 8, 10), amount="100"):
    return post_journal_entry(
        db,
        org_id,
        date=when,
        description="prueba",
        lines=[LineSpec("1100", debit=Decimal(amount)), LineSpec("4100", credit=Decimal(amount))],
        kind=kind,
    )


def test_folio_format_and_sequence(db, org):
    first = _post(db, org.id, kind="INGRESO")
    second = _post(db, org.id, kind="INGRESO")
    assert first.folio == "Ig-2026-08-0001"
    assert second.folio == "Ig-2026-08-0002"
    assert first.kind == "INGRESO"


def test_series_are_independent_per_kind(db, org):
    ingreso = _post(db, org.id, kind="INGRESO")
    egreso = _post(db, org.id, kind="EGRESO")
    diario = _post(db, org.id, kind="DIARIO")
    assert ingreso.folio == "Ig-2026-08-0001"
    assert egreso.folio == "Eg-2026-08-0001"
    assert diario.folio == "Dr-2026-08-0001"


def test_series_restart_each_month(db, org):
    agosto = _post(db, org.id, kind="EGRESO", when=date(2026, 8, 31))
    septiembre = _post(db, org.id, kind="EGRESO", when=date(2026, 9, 1))
    assert agosto.folio == "Eg-2026-08-0001"
    assert septiembre.folio == "Eg-2026-09-0001"


def test_series_are_independent_per_organization(db, org):
    other = Organization(name="Otra SA")
    db.add(other)
    db.flush()
    seed_chart_of_accounts(db, other.id)

    mine = _post(db, org.id, kind="INGRESO")
    theirs = _post(db, other.id, kind="INGRESO")
    # Mismo folio, distinta empresa: la unicidad es por organización.
    assert mine.folio == theirs.folio == "Ig-2026-08-0001"


def test_business_rules_use_expected_series(db, org):
    income = income_paid_entry(
        db, org.id, "Venta", Decimal("500"), date(2026, 8, 5), "4100", "i" * 36
    )
    expense = expense_paid_entry(
        db, org.id, "Renta", Decimal("200"), date(2026, 8, 6), "5300", "e" * 36
    )
    receivable = receivable_created_entry(
        db, org.id, "Factura", Decimal("300"), date(2026, 8, 7), "4100", "r" * 36
    )
    assert income.folio.startswith("Ig-")
    assert expense.folio.startswith("Eg-")
    # La CxC emitida devenga, no mueve efectivo: es póliza de diario.
    assert receivable.folio.startswith("Dr-")


def test_reversal_gets_its_own_folio(db, org):
    original = receivable_created_entry(
        db, org.id, "Factura", Decimal("300"), date(2026, 8, 7), "4100", "r" * 36
    )
    reversal = reversal_of(db, org.id, original, "Cancelación: Factura", date(2026, 8, 8))
    assert reversal.folio != original.folio
    assert reversal.folio.startswith("Dr-")


def test_folio_visible_in_api(client):
    from tests.helpers import auth_headers, register

    body = register(client, initial_cash="1000")
    headers = auth_headers(body)
    entries = client.get("/api/accounting/journal-entries", headers=headers).json()
    assert entries["total"] >= 1
    # El saldo inicial es póliza de diario.
    assert entries["items"][0]["folio"].startswith("Dr-")
    assert entries["items"][0]["kind"] == "DIARIO"
