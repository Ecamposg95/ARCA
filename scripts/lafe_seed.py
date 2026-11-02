"""Siembra las unidades de negocio y los contribuyentes de LaFe en una empresa existente.

Diez unidades con tipo y los alias con los que Toronja las nombra (hoja 13 del
Registro Contable), dos contribuyentes (Liza y Ale), la caja central y una caja
de efectivo por unidad con ventas, ligada a su unidad. Sin saldos: el histórico
entra por importación, no por aquí.

    python scripts/lafe_seed.py --url https://arca-production-d769.up.railway.app \
        --email liza@lafe.mx --password '...'

Idempotente por nombre: correrlo dos veces no duplica nada; lo que ya existe se
deja como está (salvo Cumbres, que siempre queda inactiva).
"""

from __future__ import annotations

import argparse
import sys

import httpx

# (nombre, tipo, alias de Toronja, abrió el, activa, tiene caja con ventas)
UNIDADES = (
    ("Centro Médico", "MATRIZ", ("CENTRO MÉDICO",), None, True, True),
    ("Alameda", "TOMA_MUESTRA", ("ALAMEDA",), None, True, True),
    ("Morelos", "TOMA_MUESTRA", ("MORELOS",), None, True, True),
    ("Rodolfo Landeros", "TOMA_MUESTRA", ("RODOLFO LANDEROS",), None, True, True),
    ("Santa Anita", "TOMA_MUESTRA", ("SANTA ANITA",), None, True, True),
    ("Villas de Nuestra Señora", "TOMA_MUESTRA", ("VILLAS DE NUESTRA SEÑORA", "VNSA"), None, True, True),
    ("Haciendas", "TOMA_MUESTRA", ("HACIENDAS",), "2026-06-01", True, True),
    ("Unidad Móvil", "UNIDAD_MOVIL", ("CENTRO MOVIL", "MORELOS MOVIL", "VNSA MOVIL"), "2026-05-01", True, True),
    # Cerrada: sólo vendió en enero. Se conserva para que su historial filtre.
    ("Cumbres", "TOMA_MUESTRA", ("CUMBRES",), None, False, False),
    # Canal Empresas: tickets con 100 % de descuento; RN-14 pide venta a crédito.
    ("Empresas", "CANAL", ("EMPRESAS",), None, True, False),
    # Vendedores de Toronja que no son una sucursal: la dirección y el sistema.
    ("Laboratorio / Dirección", "OTRA", ("Liza Díaz de León", "Soporte Técnico del Sistema"), None, True, False),
)  # fmt: skip

CONTRIBUYENTES = (
    ("Liza", "Persona física con actividad empresarial"),
    ("Ale", "RESICO"),
)

CAJA_CENTRAL = "Caja central"


def main() -> None:
    parser = argparse.ArgumentParser(description="Unidades, contribuyentes y cajas de LaFe")
    parser.add_argument("--url", default="http://localhost:8000", help="ARCA base URL")
    parser.add_argument("--email", required=True, help="Correo de un OWNER o ADMIN de la empresa")
    parser.add_argument("--password", required=True)
    parser.add_argument("--organization-id", default=None, help="Si el usuario tiene varias empresas")
    args = parser.parse_args()

    http = httpx.Client(base_url=f"{args.url.rstrip('/')}/api", timeout=60)

    def call(method: str, path: str, headers: dict | None = None, **kwargs):
        response = http.request(method, path, headers=headers or {}, **kwargs)
        if response.status_code >= 400:
            sys.exit(f"{method} {path}: {response.status_code} {response.text}")
        return response.json() if response.content else None

    auth = call("POST", "/auth/login", json={"email": args.email, "password": args.password})
    organization_id = args.organization_id or (auth.get("organization") or {}).get("id")
    if not organization_id:
        sys.exit("El usuario tiene varias empresas: indica --organization-id.")
    headers = {"Authorization": f"Bearer {auth['access_token']}", "X-Organization-ID": organization_id}

    # --- Unidades (por nombre) ---
    existing = {u["name"].lower(): u for u in call("GET", "/business-units?limit=200", headers)["items"]}
    units: dict[str, dict] = {}
    for name, kind, aliases, opened_on, _active, _with_cash in UNIDADES:
        unit = existing.get(name.lower())
        if unit is None:
            payload = {"name": name, "kind": kind, "aliases": list(aliases)}
            if opened_on:
                payload["opened_on"] = opened_on
            unit = call("POST", "/business-units", headers, json=payload)
            print(f"  + unidad {name} ({kind})")
        else:
            print(f"  = unidad {name}")
        units[name] = unit

    # --- Contribuyentes (por nombre) ---
    existing = {e["name"].lower(): e for e in call("GET", "/fiscal-entities?limit=200", headers)["items"]}
    for name, regime in CONTRIBUYENTES:
        if name.lower() in existing:
            print(f"  = contribuyente {name}")
            continue
        call("POST", "/fiscal-entities", headers, json={"name": name, "regime": regime})
        print(f"  + contribuyente {name} ({regime})")

    # --- Cajas (por nombre), antes de apagar Cumbres: una unidad inactiva no acepta cajas ---
    accounts = {a["name"].lower(): a for a in call("GET", "/accounts", headers)}
    if CAJA_CENTRAL.lower() not in accounts:
        call("POST", "/accounts", headers, json={"name": CAJA_CENTRAL, "type": "CASH"})
        print(f"  + {CAJA_CENTRAL}")
    for name, _kind, _aliases, _opened_on, _active, with_cash in UNIDADES:
        if not with_cash:
            continue
        caja = f"Caja {name}"
        if caja.lower() in accounts:
            continue
        call("POST", "/accounts", headers, json={"name": caja, "type": "CASH", "business_unit_id": units[name]["id"]})
        print(f"  + {caja}")

    # --- Cumbres cerrada ---
    for name, _kind, _aliases, _opened_on, active, _with_cash in UNIDADES:
        if not active and units[name]["active"]:
            call("PATCH", f"/business-units/{units[name]['id']}", headers, json={"active": False})
            print(f"  ~ unidad {name} desactivada")

    print("Listo.")


if __name__ == "__main__":
    main()
