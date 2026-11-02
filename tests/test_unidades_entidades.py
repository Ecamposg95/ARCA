"""Unidades de negocio y entidad fiscal: dos dimensiones opcionales del libro.

Una empresa sin unidades ni entidades sigue exactamente igual que hoy; con
ellas, cada operación y su póliza las heredan y los reportes se filtran.
"""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com", initial_cash="100000"):
    body = register(client, email=email, initial_cash=initial_cash)
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    nomina = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Nómina"
    )
    return headers, account, ventas, nomina


def _unit(client, headers, name, **extra):
    response = client.post("/api/business-units", headers=headers, json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _entity(client, headers, name, **extra):
    response = client.post("/api/fiscal-entities", headers=headers, json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


# --- Catálogos -----------------------------------------------------------------


def test_business_unit_derives_code_and_lists(client):
    headers, *_ = _setup(client)
    unit = _unit(client, headers, "Morelos", kind="TOMA_MUESTRA", aliases=["MORELOS"])
    assert unit["code"] == "MORELOS"
    assert unit["kind"] == "TOMA_MUESTRA"
    assert unit["active"] is True
    assert unit["accounts_count"] == 0

    page = client.get("/api/business-units", headers=headers).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == unit["id"]


def test_business_unit_name_is_unique_case_insensitive(client):
    headers, *_ = _setup(client)
    _unit(client, headers, "Morelos")
    response = client.post("/api/business-units", headers=headers, json={"name": "  morelos "})
    assert response.status_code == 400
    assert "Morelos" in response.json()["detail"] or "unidad" in response.json()["detail"].lower()


def test_only_one_active_matriz(client):
    headers, *_ = _setup(client)
    _unit(client, headers, "Centro Médico", kind="MATRIZ")
    response = client.post("/api/business-units", headers=headers, json={"name": "Otra", "kind": "MATRIZ"})
    assert response.status_code == 400
    assert "matriz" in response.json()["detail"].lower()


def test_alias_is_normalized_and_unique_within_org(client):
    headers, *_ = _setup(client)
    _unit(client, headers, "Villas", aliases=["VILLAS DE NUESTRA SEÑORA", "VNSA MOVIL"])
    # Mismo alias con acentos, minúsculas y espacios de más: es el mismo.
    response = client.post(
        "/api/business-units",
        headers=headers,
        json={"name": "Unidad Móvil", "aliases": ["vnsa   móvil"]},
    )
    assert response.status_code == 400
    assert "alias" in response.json()["detail"].lower()


def test_business_unit_patch_and_deactivate(client):
    headers, *_ = _setup(client)
    unit = _unit(client, headers, "Cumbres")
    response = client.patch(
        f"/api/business-units/{unit['id']}",
        headers=headers,
        json={"active": False, "opened_on": "2026-01-01", "aliases": ["CUMBRES"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is False
    assert response.json()["opened_on"] == "2026-01-01"

    active_only = client.get("/api/business-units?active=true", headers=headers).json()
    assert active_only["total"] == 0


def test_fiscal_entity_crud(client):
    headers, *_ = _setup(client)
    entity = _entity(client, headers, "Liza", tax_id="dial900101ab1", regime="Persona física con actividad empresarial")
    assert entity["tax_id"] == "DIAL900101AB1"
    page = client.get("/api/fiscal-entities", headers=headers).json()
    assert page["total"] == 1

    response = client.patch(f"/api/fiscal-entities/{entity['id']}", headers=headers, json={"regime": "RESICO"})
    assert response.status_code == 200
    assert response.json()["regime"] == "RESICO"

    response = client.post("/api/fiscal-entities", headers=headers, json={"name": "liza"})
    assert response.status_code == 400


def test_catalogs_are_tenant_isolated(client):
    headers_a, *_ = _setup(client, email="a@example.com")
    headers_b, *_ = _setup(client, email="b@example.com")
    unit_b = _unit(client, headers_b, "Sucursal B")
    entity_b = _entity(client, headers_b, "Contribuyente B")

    assert client.get("/api/business-units", headers=headers_a).json()["total"] == 0
    assert client.get("/api/fiscal-entities", headers=headers_a).json()["total"] == 0
    assert client.patch(f"/api/business-units/{unit_b['id']}", headers=headers_a, json={"name": "x"}).status_code == 404
    assert client.patch(f"/api/fiscal-entities/{entity_b['id']}", headers=headers_a, json={"name": "x"}).status_code == 404


def test_organization_exposes_dimension_flags(client):
    headers, *_ = _setup(client)
    current = client.get("/api/organizations/current", headers=headers).json()
    assert current["has_business_units"] is False
    assert current["has_fiscal_entities"] is False

    _unit(client, headers, "Morelos")
    _entity(client, headers, "Liza")
    current = client.get("/api/organizations/current", headers=headers).json()
    assert current["has_business_units"] is True
    assert current["has_fiscal_entities"] is True


def test_viewer_cannot_write_catalogs(client):
    headers, *_ = _setup(client)
    client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": "viewer@example.com", "name": "Lector", "role": "VIEWER", "password": "supersegura123"},
    )
    login = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "supersegura123"})
    assert login.status_code == 200, login.text
    viewer_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Organization-ID": headers["X-Organization-ID"],
    }
    assert client.get("/api/business-units", headers=viewer_headers).status_code == 200
    assert client.post("/api/business-units", headers=viewer_headers, json={"name": "x"}).status_code == 403
