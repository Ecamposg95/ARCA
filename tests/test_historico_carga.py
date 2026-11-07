"""Histórico de análisis: tablas, reemplazo por rango y aislamiento del libro."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.domains.analytics.points import Point, ResolvedPoint, replace_points
from app.models.financial_account import FinancialAccount
from app.models.historical import HistoricalLoad, HistoricalPoint
from tests.helpers import auth_headers, register


@pytest.fixture()
def org(client):
    body = register(client, email="historico@example.com", initial_cash="1000")
    return body["organization"]["id"], auth_headers(body)


def _pt(day: date, value: str, metric: str = "net_sales") -> ResolvedPoint:
    return ResolvedPoint(
        dataset="sales_daily",
        metric=metric,
        period_start=day,
        period_grain="day",
        value=Decimal(value),
        unit_label="VILLAS",
    )


def _counts(db, organization_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for point in db.query(HistoricalPoint).filter(HistoricalPoint.organization_id == organization_id).all():
        family = point.source.split(":", 1)[0]
        counts[family] = counts.get(family, 0) + 1
    return counts


def test_replace_points_reemplaza_solo_el_rango_y_la_familia(db, org):
    organization_id, _ = org
    replace_points(
        db,
        organization_id,
        source_family="toronja",
        source="toronja:v.xls#1",
        points=[
            _pt(date(2026, 1, 5), "100"),
            _pt(date(2026, 1, 20), "200"),
            _pt(date(2026, 2, 3), "300"),
            _pt(date(2026, 2, 10), "400"),
        ],
        user_id=None,
    )
    replace_points(
        db,
        organization_id,
        source_family="control_general",
        source="control_general:cg.xlsx#PROY",
        points=[_pt(date(2026, 1, 1), "999")],
        user_id=None,
    )
    replace_points(
        db,
        organization_id,
        source_family="toronja",
        source="toronja:v2.xls#1",
        points=[_pt(date(2026, 2, 3), "350"), _pt(date(2026, 3, 1), "500")],
        user_id=None,
    )

    assert _counts(db, organization_id) == {"toronja": 4, "control_general": 1}
    toronja = (
        db.query(HistoricalPoint)
        .filter(HistoricalPoint.organization_id == organization_id, HistoricalPoint.source.like("toronja:%"))
        .order_by(HistoricalPoint.period_start)
        .all()
    )
    assert [(p.period_start, p.value) for p in toronja] == [
        (date(2026, 1, 5), Decimal("100.00")),
        (date(2026, 1, 20), Decimal("200.00")),
        (date(2026, 2, 3), Decimal("350.00")),
        (date(2026, 3, 1), Decimal("500.00")),
    ]


def test_recargar_igual_deja_el_mismo_conteo(db, org):
    organization_id, _ = org
    points = [_pt(date(2026, 1, 5), "100"), _pt(date(2026, 1, 5), "2", metric="tickets")]
    first = replace_points(db, organization_id, source_family="toronja", source="toronja:v.xls#1", points=points, user_id=None)
    second = replace_points(db, organization_id, source_family="toronja", source="toronja:v.xls#1", points=points, user_id=None)

    assert _counts(db, organization_id) == {"toronja": 2}
    loads = db.query(HistoricalLoad).filter(HistoricalLoad.organization_id == organization_id).all()
    assert {load.id for load in loads} == {first.id, second.id}
    assert first.rows == 2 and first.period_from == date(2026, 1, 5) and first.period_to == date(2026, 1, 5)


def test_historico_no_toca_la_contabilidad(db, org, client):
    organization_id, headers = org
    before = client.get("/api/accounting/trial-balance", headers=headers).json()
    balances_before = sum(
        (acc.current_balance for acc in db.query(FinancialAccount).filter_by(organization_id=organization_id)),
        Decimal("0"),
    )

    replace_points(
        db,
        organization_id,
        source_family="toronja",
        source="toronja:v.xls#1",
        points=[_pt(date(2026, 1, 5), "100000")],
        user_id=None,
    )

    after = client.get("/api/accounting/trial-balance", headers=headers).json()
    balances_after = sum(
        (acc.current_balance for acc in db.query(FinancialAccount).filter_by(organization_id=organization_id)),
        Decimal("0"),
    )
    assert after == before
    assert balances_after == balances_before == Decimal("1000.00")


def test_otra_empresa_no_ve_los_puntos(db, org, client):
    organization_id, _ = org
    other = register(client, email="otra@example.com")["organization"]["id"]
    replace_points(db, organization_id, source_family="toronja", source="toronja:v.xls#1", points=[_pt(date(2026, 1, 5), "1")], user_id=None)
    assert db.query(HistoricalPoint).filter_by(organization_id=other).count() == 0


def test_point_es_inmutable_y_sin_ids():
    point = Point(dataset="sales_daily", metric="net_sales", period_start=date(2026, 1, 1), period_grain="day", value=Decimal("1"))
    with pytest.raises(FrozenInstanceError):
        point.value = Decimal("2")  # type: ignore[misc]


# --- Endpoint y script de carga -------------------------------------------


def _member(client, owner_headers, email, role):
    response = client.post(
        "/api/organizations/current/members",
        headers=owner_headers,
        json={"email": email, "name": role, "role": role, "password": "supersegura123"},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={"email": email, "password": "supersegura123"})
    return auth_headers(login.json())


def _toronja_file():
    from tests.toronja_fixture import render_html, ticket

    return render_html([ticket("0201260001", "2026-01-02", "VILLAS", efectivo="100")])


def _upload(client, headers, files: dict, dry_run: bool = False):
    return client.post(
        "/api/admin/historical-loads",
        headers=headers,
        files={family: (name, content) for family, (name, content) in files.items()},
        data={"dry_run": "true" if dry_run else "false"},
    )


def test_carga_solo_owner(client, org):
    organization_id, owner = org
    admin = _member(client, owner, "admin@example.com", "ADMIN")
    assert _upload(client, admin, {"toronja": ("v.xls", _toronja_file())}).status_code == 403
    response = _upload(client, owner, {"toronja": ("v.xls", _toronja_file())})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["dry_run"] is False
    assert body["loads"][0]["family"] == "toronja" and body["loads"][0]["rows"] > 0
    assert body["loads"][0]["period_from"] == "2026-01-02"
    assert body["unresolved_units"] == ["VILLAS"]


def test_carga_dry_run_no_guarda(client, db, org):
    organization_id, owner = org
    response = _upload(client, owner, {"toronja": ("v.xls", _toronja_file())}, dry_run=True)
    assert response.status_code == 201, response.text
    assert response.json()["dry_run"] is True and response.json()["loads"][0]["rows"] > 0
    assert db.query(HistoricalPoint).filter_by(organization_id=organization_id).count() == 0
    assert client.get("/api/admin/historical-loads", headers=owner).json() == []


def test_carga_sin_archivos_400(client, org):
    _, owner = org
    response = client.post("/api/admin/historical-loads", headers=owner, data={"dry_run": "false"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Sube al menos un archivo"


def test_archivo_equivocado_400_en_espanol(client, org):
    _, owner = org
    response = _upload(client, owner, {"control_general": ("v.xls", _toronja_file())})
    assert response.status_code == 400
    assert "CONTROL GENERAL" in response.json()["detail"]
    response = _upload(client, owner, {"toronja": ("cg.xlsx", b"PK\x03\x04basura")})
    assert response.status_code == 400 and "Toronja" in response.json()["detail"]


def test_otra_empresa_no_ve_las_cargas(client, org):
    _, owner = org
    assert _upload(client, owner, {"toronja": ("v.xls", _toronja_file())}).status_code == 201
    mine = client.get("/api/admin/historical-loads", headers=owner).json()
    assert len(mine) == 1 and mine[0]["source"] == "toronja:v.xls#ventas" and mine[0]["rows"] > 0
    other = register(client, email="ajena@example.com")
    assert client.get("/api/admin/historical-loads", headers=auth_headers(other)).json() == []
    accountant = _member(client, owner, "conta@example.com", "ACCOUNTANT")
    assert client.get("/api/admin/historical-loads", headers=accountant).status_code == 200
    member = _member(client, owner, "aux@example.com", "MEMBER")
    assert client.get("/api/admin/historical-loads", headers=member).status_code == 403


def test_script_carga_por_nombre_de_empresa(db, org, tmp_path, capsys):
    organization_id, _ = org
    from scripts.lafe_historico import main

    path = tmp_path / "ventas.xls"
    path.write_bytes(_toronja_file())
    report = main(["--org", "Mi Changarro", "--toronja", str(path), "--dry-run"], db=db)
    assert report.dry_run is True and report.loads[0]["rows"] > 0
    assert db.query(HistoricalPoint).filter_by(organization_id=organization_id).count() == 0
    report = main(["--org", organization_id, "--toronja", str(path)], db=db)
    assert report.dry_run is False
    assert db.query(HistoricalPoint).filter_by(organization_id=organization_id).count() == report.loads[0]["rows"]
    out = capsys.readouterr().out
    assert "toronja" in out and "VILLAS" in out
