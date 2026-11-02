"""La semilla de LaFe deja las unidades, los contribuyentes y las cajas; correrla dos veces no duplica."""

import sys

from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from scripts import lafe_seed
from tests.helpers import auth_headers, register


def test_lafe_seed_is_idempotent(client, monkeypatch):
    body = register(client, email="liza@lafe.mx", business="LaFe")
    headers = auth_headers(body)

    # El script habla HTTP con httpx; aquí habla con la app en memoria.
    monkeypatch.setattr(
        lafe_seed.httpx,
        "Client",
        lambda base_url, timeout: TestClient(fastapi_app, base_url=base_url),
    )
    monkeypatch.setattr(
        sys, "argv", ["lafe_seed", "--url", "http://testserver", "--email", "liza@lafe.mx", "--password", "supersegura123"]
    )
    lafe_seed.main()
    lafe_seed.main()

    units = client.get("/api/business-units?limit=200", headers=headers).json()["items"]
    assert len(units) == len(lafe_seed.UNIDADES)
    by_name = {unit["name"]: unit for unit in units}
    assert by_name["Centro Médico"]["kind"] == "MATRIZ"
    assert by_name["Cumbres"]["active"] is False
    assert by_name["Empresas"]["kind"] == "CANAL"
    assert "VNSA MOVIL" in by_name["Unidad Móvil"]["aliases"]
    assert by_name["Morelos"]["accounts_count"] == 1

    entities = client.get("/api/fiscal-entities", headers=headers).json()["items"]
    assert {e["name"]: e["regime"] for e in entities} == {"Liza": "Persona física con actividad empresarial", "Ale": "RESICO"}

    accounts = client.get("/api/accounts", headers=headers).json()
    names = {account["name"] for account in accounts}
    assert "Caja central" in names and "Caja Morelos" in names and "Caja Cumbres" not in names
    assert all(account["current_balance"] == "0.00" for account in accounts if account["name"].startswith("Caja "))
