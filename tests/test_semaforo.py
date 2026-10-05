"""Semáforo de la cartera: regla pura, sin base de datos."""

from datetime import date
from decimal import Decimal

from app.domains.portfolio.status import portfolio_status, previous_month


def _status(**overrides):
    params = {
        "today": date(2026, 10, 5),
        "previous_month_active": True,
        "previous_month_closed": True,
        "payable_overdue": Decimal("0"),
        "pending_proposals": 0,
    }
    params.update(overrides)
    return portfolio_status(**params)


def test_everything_in_order_is_green():
    assert _status() == ("green", [])


def test_open_previous_month_is_amber_until_the_17th():
    status, reasons = _status(previous_month_closed=False)
    assert status == "amber"
    assert reasons == ["Septiembre sigue sin cerrar"]


def test_day_17_is_still_amber():
    status, _reasons = _status(today=date(2026, 10, 17), previous_month_closed=False)
    assert status == "amber"


def test_open_previous_month_turns_red_after_the_17th():
    status, _reasons = _status(today=date(2026, 10, 18), previous_month_closed=False)
    assert status == "red"


def test_a_month_without_entries_has_nothing_to_close():
    result = _status(
        today=date(2026, 10, 25), previous_month_active=False, previous_month_closed=False
    )
    assert result == ("green", [])


def test_overdue_payables_are_red():
    status, reasons = _status(payable_overdue=Decimal("12400"))
    assert status == "red"
    assert reasons == ["$12,400.00 por pagar vencidos"]


def test_pending_proposals_are_amber():
    assert _status(pending_proposals=3) == ("amber", ["3 propuestas por revisar"])


def test_one_proposal_reads_in_singular():
    assert _status(pending_proposals=1) == ("amber", ["1 propuesta por revisar"])


def test_reasons_list_every_cause_not_only_the_deciding_one():
    status, reasons = _status(
        previous_month_closed=False, payable_overdue=Decimal("500"), pending_proposals=2
    )
    assert status == "red"
    assert reasons == [
        "Septiembre sigue sin cerrar",
        "$500.00 por pagar vencidos",
        "2 propuestas por revisar",
    ]


def test_january_looks_back_to_december_of_the_previous_year():
    assert previous_month(date(2027, 1, 10)) == (2026, 12)
    _status_value, reasons = _status(today=date(2027, 1, 10), previous_month_closed=False)
    assert reasons == ["Diciembre sigue sin cerrar"]
