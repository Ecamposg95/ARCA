"""Precios, costo por llamada y presupuesto mensual del asistente (spec 2026-11-02 §Costo)."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.assistant import AiUsage
from app.models.organization import Organization
from app.services.ai import budget as B
from app.services.ai.pricing import cost_usd, price_for


def _usage(**kw):
    base = dict(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_costo_opus_por_tipo_de_token():
    # 1M de cada tipo = la tarifa tal cual.
    assert cost_usd("claude-opus-5-5", _usage(input_tokens=1_000_000)) == Decimal("4.000000")
    assert cost_usd("claude-opus-5-5", _usage(output_tokens=1_000_000)) == Decimal("20.000000")
    assert cost_usd("claude-opus-5-5", _usage(cache_read_input_tokens=1_000_000)) == Decimal("0.200000")
    assert cost_usd("claude-opus-5-5", _usage(cache_creation_input_tokens=1_000_000)) == Decimal("5.000000")


def test_costo_de_una_llamada_tipica_suma_todo():
    usage = _usage(input_tokens=1_000, output_tokens=500, cache_read_input_tokens=8_000, cache_creation_input_tokens=0)
    # 1000*4 + 500*20 + 8000*0.20 = 4000 + 10000 + 1600 = 15600 / 1e6
    assert cost_usd("claude-opus-5-5", usage) == Decimal("0.015600")


def test_sonnet_y_haiku_tienen_su_tarifa_y_desconocido_cobra_como_opus():
    assert cost_usd("claude-sonnet-5-5", _usage(output_tokens=1_000_000)) == Decimal("10.000000")
    assert cost_usd("claude-haiku-5-5", _usage(output_tokens=1_000_000)) == Decimal("0.500000")
    assert price_for("modelo-raro") == price_for("claude-opus-5-5")
    assert price_for("claude-sonnet-5") == price_for("claude-sonnet-5-5")


def test_usage_puede_venir_como_dict():
    assert cost_usd("claude-opus-5-5", {"input_tokens": 1_000_000}) == Decimal("4.000000")


def test_mes_calendario_en_mexico():
    # 1 de nov 03:00 UTC es todavía 31 de oct en México: pertenece a octubre.
    start, end = B.month_bounds(datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc))
    assert start == datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
    start, end = B.month_bounds(datetime(2026, 12, 15, tzinfo=timezone.utc))
    assert end.astimezone(B.MEXICO).month == 1


@pytest.fixture()
def org(db):
    organization = Organization(name="La Fe")
    db.add(organization)
    db.commit()
    return organization


def _usage_row(org_id, cost, when, user_id=None):
    return AiUsage(organization_id=org_id, user_id=user_id, model="claude-opus-5-5", cost_usd=Decimal(cost),
                   created_at=when)


def test_consumo_del_mes_solo_suma_el_mes_y_la_empresa(db, org):
    other = Organization(name="Otra")
    db.add(other)
    db.commit()
    now = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
    db.add_all([
        _usage_row(org.id, "0.50", datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)),
        _usage_row(org.id, "0.25", datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)),
        _usage_row(org.id, "9.00", datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)),   # mes anterior
        _usage_row(other.id, "9.00", datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)),  # otra empresa
    ])
    db.commit()
    assert B.month_spend(db, org.id, now) == Decimal("0.750000")
    assert B.month_spend(db, other.id, now) == Decimal("9.000000")


def test_tope_por_default_y_por_empresa(db, org):
    status = B.budget_status(db, org)
    assert status.budget_usd == Decimal("20")
    assert status.spent_usd == 0 and status.remaining_usd == Decimal("20") and not status.exhausted
    org.ai_budget_usd = Decimal("1.00")
    db.add(_usage_row(org.id, "0.995", datetime.now(timezone.utc)))
    db.commit()
    status = B.budget_status(db, org)
    assert status.exhausted
    with pytest.raises(B.BudgetExhausted) as exc:
        B.ensure_budget(db, org)
    assert "Se agotó el presupuesto del asistente de este mes (1.00 de 1.00 USD)" in str(exc.value)
