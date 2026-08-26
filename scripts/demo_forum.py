"""Prepara el escenario del demo de foro contra cualquier ARCA.

Crea una empresa con historia creíble —cuatro meses de operación de una
consultora de software— para que el tablero, los reportes y la cartera se vean
llenos desde el primer segundo, y deja lista una llave de agente para el acto
del MCP.

    python scripts/demo_forum.py --url https://arca-production-d769.up.railway.app

Cada corrida crea una empresa NUEVA (correo con marca de tiempo), así que se
puede ensayar tantas veces como haga falta sin borrar nada ni pisar la anterior.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta

import httpx

CUSTOMERS = (
    "Grupo Industrial del Norte",
    "Fintech Pagos MX",
    "Clínica Los Álamos",
    "Retail Vega",
    "Constructora Ríos",
)
VENDORS = (
    "WeWork Reforma",
    "Amazon Web Services",
    "Google Workspace",
    "Despacho Contable Núñez",
    "Telmex Negocios",
)
INCOME_MIX = (
    ("Desarrollo de software", "Servicios"),
    ("Proyecto web", "Servicios"),
    ("Iguala mensual de soporte", "Servicios"),
    ("Consultoría técnica", "Servicios"),
    ("Implementación ERP", "Ventas"),
)
# (concepto, categoría, proveedor, mínimo, máximo, causa IVA)
# El proveedor va amarrado al concepto: "Renta coworking · Google Workspace"
# se ve descuidado en un proyector, y el público lo nota antes que tú.
EXPENSE_MIX = (
    ("Nómina quincenal", "Nómina", None, 38000, 52000, False),
    ("Renta coworking", "Renta", "WeWork Reforma", 15000, 21000, True),
    ("Factura AWS", "Software", "Amazon Web Services", 4000, 12000, True),
    ("Publicidad LinkedIn", "Marketing", "Google Workspace", 2000, 8000, True),
    ("Honorarios contables", "Honorarios", "Despacho Contable Núñez", 3500, 6000, True),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Escenario para el demo de foro")
    parser.add_argument("--url", default="http://localhost:8000", help="ARCA base URL")
    parser.add_argument("--password", default="demoforo2026")
    args = parser.parse_args()

    random.seed(7)  # mismos montos en cada ensayo
    # El correo lleva la hora para que dos ensayos del mismo día no choquen.
    email = f"demo{datetime.now().strftime('%m%d%H%M')}@atlas.mx"
    client = httpx.Client(base_url=f"{args.url.rstrip('/')}/api", timeout=60)

    registro = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": args.password,
            "name": "Emmanuel Campos",
            "business_name": "Atlas Software Consulting",
            "business_type": "services",
            "initial_cash": "25000",
        },
    )
    if registro.status_code != 201:
        sys.exit(f"No se pudo crear la empresa: {registro.status_code} {registro.text}")
    auth = registro.json()
    client.headers.update(
        {
            "Authorization": f"Bearer {auth['access_token']}",
            "X-Organization-ID": auth["organization"]["id"],
        }
    )

    def post(path: str, payload: dict) -> dict:
        response = client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    # --- Instrumentos: efectivo, banco y una tarjeta con límite ---
    bbva = post("/accounts", {"name": "BBVA Empresarial", "type": "BANK",
                              "opening_balance": "180000", "institution": "BBVA"})
    post("/accounts", {"name": "Santander Nómina", "type": "BANK",
                       "opening_balance": "90000", "institution": "Santander"})
    amex = post("/accounts", {"name": "AMEX Corporativa", "type": "CREDIT_CARD",
                              "credit_limit": "150000", "institution": "American Express"})

    customers = {name: post("/customers", {"name": name}) for name in CUSTOMERS}
    vendors = {name: post("/vendors", {"name": name}) for name in VENDORS}

    income_cats = {c["name"]: c for c in client.get("/categories", params={"kind": "INCOME"}).json()}
    expense_cats = {c["name"]: c for c in client.get("/categories", params={"kind": "EXPENSE"}).json()}

    today = date.today()

    def day_of(months_ago: int, day: int) -> str:
        index = today.year * 12 + (today.month - 1) - months_ago
        year, month = divmod(index, 12)
        return min(date(year, month + 1, min(day, 28)), today).isoformat()

    # --- Cuatro meses de operación ---
    for months_ago in range(3, -1, -1):
        for _ in range(random.randint(2, 3)):
            description, category = random.choice(INCOME_MIX)
            post("/income", {
                "date": day_of(months_ago, random.randint(3, 26)),
                "description": description,
                "amount": str(random.randrange(45000, 180000, 5000)),
                "tax_rate": "0.16",
                "category_id": income_cats[category]["id"],
                "customer_id": customers[random.choice(CUSTOMERS)]["id"],
                "financial_account_id": bbva["id"],
                "status": "PAID",
            })
        for description, category, vendor, low, high, taxed in EXPENSE_MIX:
            for day in (14, 28) if category == "Nómina" else (random.randint(2, 12),):
                payload = {
                    "date": day_of(months_ago, day),
                    "description": description,
                    "amount": str(random.randint(low, high)),
                    "tax_rate": "0.16" if taxed else "0",
                    "category_id": expense_cats[category]["id"],
                    "financial_account_id": bbva["id"],
                    "status": "PAID",
                }
                # La nómina no tiene proveedor: la paga la empresa a su gente.
                if vendor:
                    payload["vendor_id"] = vendors[vendor]["id"]
                post("/expenses", payload)

    # --- Un gasto con tarjeta: crea deuda, no toca el banco (acto 3) ---
    licencias = post("/expenses", {
        "date": day_of(0, 12),
        "description": "Licencias anuales del equipo",
        "amount": "34800",
        "tax_rate": "0.16",
        "category_id": expense_cats["Software"]["id"],
        "vendor_id": vendors["Amazon Web Services"]["id"],
        "financial_account_id": amex["id"],
        "status": "PAID",
    })

    # --- Cartera: una vencida y una cobrada a medias (actos 3 y 5) ---
    post("/receivables", {
        "customer_id": customers["Retail Vega"]["id"],
        "description": "Factura F-0075 — mantenimiento anual",
        "amount": "52200",
        "tax_rate": "0.16",
        "date": (today - timedelta(days=52)).isoformat(),
        "due_date": (today - timedelta(days=22)).isoformat(),
        "category_id": income_cats["Servicios"]["id"],
    })
    parcial = post("/receivables", {
        "customer_id": customers["Grupo Industrial del Norte"]["id"],
        "description": "Factura F-0087 — ERP fase 2",
        "amount": "174000",
        "tax_rate": "0.16",
        "date": (today - timedelta(days=8)).isoformat(),
        "due_date": (today + timedelta(days=22)).isoformat(),
        "category_id": income_cats["Ventas"]["id"],
    })
    post(f"/receivables/{parcial['id']}/collect",
         {"amount": "87000", "financial_account_id": bbva["id"]})

    for vendor, description, amount, days, category in (
        ("Amazon Web Services", "Factura AWS del mes", "9860", 12, "Software"),
        ("Despacho Contable Núñez", "Iguala del despacho", "5220", 18, "Honorarios"),
    ):
        post("/payables", {
            "vendor_id": vendors[vendor]["id"],
            "description": description,
            "amount": amount,
            "tax_rate": "0.16",
            "due_date": (today + timedelta(days=days)).isoformat(),
            "category_id": expense_cats[category]["id"],
        })

    # --- Patrimonio: lo que se compró para usar años y lo que se debe a plazos ---
    post("/fixed-assets", {
        "name": "MacBook Pro del equipo de diseño",
        "category": "EQUIPO_COMPUTO",
        "acquisition_date": day_of(3, 8),
        "cost": "58000",
        "tax_amount": "9280",
        "useful_life_months": 36,
        "financial_account_id": bbva["id"],
    })
    post("/fixed-assets", {
        "name": "Camioneta de reparto",
        "category": "VEHICULOS",
        "acquisition_date": day_of(3, 3),
        "cost": "420000",
        "tax_amount": "67200",
        "salvage_value": "60000",
        "useful_life_months": 48,
        "financial_account_id": bbva["id"],
    })
    # Se corren sólo los meses ya cerrados: depreciar el mes en curso asentaría
    # una póliza con fecha futura y ARCA lo rechaza, con razón.
    for months_ago in range(2, 0, -1):
        index = today.year * 12 + (today.month - 1) - months_ago
        year, month = divmod(index, 12)
        client.post("/fixed-assets/depreciate", json={"year": year, "month": month + 1})

    prestamo = post("/loans", {
        "lender": "BBVA",
        "description": "Crédito para capital de trabajo",
        "principal": "300000",
        "annual_rate": "0.22",
        "term_months": 24,
        "start_date": day_of(2, 1),
        "financial_account_id": bbva["id"],
    })
    for months_ago in (1, 0):
        post(f"/loans/{prestamo['id']}/pay", {
            "amount": str(prestamo["monthly_payment"]),
            "financial_account_id": bbva["id"],
            "date": day_of(months_ago, 1),
        })

    # --- Proyectos: uno que deja dinero y uno que se lo come ---
    erp = post("/projects", {
        "name": "ERP fase 2 — Grupo Industrial",
        "budget": "400000",
        "customer_id": customers["Grupo Industrial del Norte"]["id"],
    })
    portal = post("/projects", {
        "name": "Portal de clientes — Fintech Pagos",
        "budget": "180000",
        "customer_id": customers["Fintech Pagos MX"]["id"],
    })
    for project_id, ingreso, costo in ((erp["id"], "232000", "98000"), (portal["id"], "69600", "84000")):
        post("/income", {
            "date": day_of(1, 15),
            "description": "Entrega de proyecto",
            "amount": ingreso,
            "tax_rate": "0.16",
            "category_id": income_cats["Servicios"]["id"],
            "financial_account_id": bbva["id"],
            "status": "PAID",
            "project_id": project_id,
        })
        post("/expenses", {
            "date": day_of(1, 20),
            "description": "Equipo asignado al proyecto",
            "amount": costo,
            "tax_rate": "0",
            "category_id": expense_cats["Nómina"]["id"],
            "financial_account_id": bbva["id"],
            "status": "PAID",
            "project_id": project_id,
        })

    # --- Llave para el acto del agente ---
    llave = post("/agent-keys", {"name": "Claude Code", "scopes": "READ,PROPOSE"})

    resumen = client.get("/dashboard/summary").json()
    proyeccion = client.get("/reports/cash-projection").json()
    balanza = client.get("/accounting/trial-balance").json()

    def folio_de(source_type: str, source_id: str) -> str:
        entries = client.get(
            "/accounting/journal-entries",
            params={"source_type": source_type, "source_id": source_id},
        ).json()["items"]
        return ", ".join(e["folio"] for e in entries) or "—"

    print("\n╭─ Escenario listo ──────────────────────────────────────")
    print(f"│ URL        {args.url}")
    print(f"│ Correo     {email}")
    print(f"│ Contraseña {args.password}")
    print("│")
    print(f"│ Disponible        {resumen['cash']}")
    print(f"│ Deuda en tarjetas {resumen['card_debt']}")
    print(f"│ Por cobrar        {resumen['receivables']} (vencido {resumen['overdue_receivables']})")
    print(f"│ Por pagar         {resumen['payables']}")
    print(f"│ Proyección 90d    {proyeccion['projected_cash']}")
    polizas = client.get("/accounting/journal-entries", params={"limit": 1}).json()["total"]
    print(f"│ Pólizas           {polizas} (balanza cuadra: "
          f"{balanza['total_debit'] == balanza['total_credit']})")
    print("│")
    activos = client.get("/fixed-assets/summary").json()
    prestamos = client.get("/loans/summary").json()
    print(f"│ Activos (valor)   {activos['book_value']}")
    print(f"│ Deuda de créditos {prestamos['outstanding']}")
    print("│")
    print("│ Pólizas que se citan en vivo:")
    print(f"│   Tarjeta AMEX (acto 3)  {folio_de('expense', licencias['id'])}")
    print(f"│   F-0087 parcial (IVA)   {folio_de('receivable', parcial['id'])}")
    print("│")
    print("│ Llave de agente (para el acto del MCP):")
    print(f"│   {llave['token']}")
    print("│")
    print("│ claude mcp add arca \\")
    print(f"│     --env ARCA_URL={args.url} \\")
    print(f"│     --env ARCA_API_KEY={llave['token']} \\")
    print("│     -- python tools/arca_mcp.py")
    print("╰────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
