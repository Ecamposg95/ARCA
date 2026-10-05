"""Prepara la cartera de un despacho contable para enseñársela a un contador.

Crea un contador con cuatro empresas, una por cada estado del semáforo:

    A  su propio despacho      al corriente (mes anterior cerrado)
    B  Ferretería El Tornillo  mes anterior sin cerrar
    C  Restaurante La Milpa    cuentas por pagar vencidas
    D  Clínica Dental Sonríe   propuestas de agentes por revisar

B y C las dio de alta el contador (él lleva al cliente). En D la dueña ya usaba
ARCA y lo invitó como contador (el cliente lo trae a él).

    python scripts/demo_despacho.py --url https://arca-production-d769.up.railway.app

Cada corrida crea cuentas NUEVAS (correo con marca de tiempo): se puede ensayar
las veces que haga falta sin pisar la anterior.

OJO con el día 17: hasta ese día B se ve "Por atender"; después, "Urgente".
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

import httpx

# Ventas: (concepto, categoría, monto). Gastos: (concepto, categoría, monto, tasa de IVA).
DESPACHO = {
    "opening": "120000",
    "incomes": (
        ("Igualas contables del mes", "Servicios", "86000"),
        ("Declaraciones anuales", "Servicios", "24000"),
    ),
    "expenses": (
        ("Nómina del despacho", "Nómina", "42000", "0"),
        ("Renta de oficina", "Renta", "13920", "0.16"),
        ("Licencias de software", "Software", "5800", "0.16"),
    ),
}
FERRETERIA = {
    "name": "Ferretería El Tornillo",
    "business_type": "commerce",
    "tax_id": "FET180312AB1",
    "opening": "95000",
    "incomes": (
        ("Ventas de mostrador, primera quincena", "Ventas", "148000"),
        ("Ventas de mostrador, segunda quincena", "Ventas", "163500"),
    ),
    "expenses": (
        ("Compra de mercancía", "Inventario", "121800", "0.16"),
        ("Nómina quincenal", "Nómina", "38000", "0"),
        ("Renta del local", "Renta", "17400", "0.16"),
    ),
}
RESTAURANTE = {
    "name": "Restaurante La Milpa",
    "business_type": "restaurant",
    "tax_id": "RLM200915KL4",
    "opening": "60000",
    "incomes": (
        ("Ventas de salón", "Ventas", "212000"),
        ("Banquetes y eventos", "Servicios", "58000"),
    ),
    "expenses": (
        ("Insumos y abarrotes", "Inventario", "96000", "0"),
        ("Nómina quincenal", "Nómina", "54000", "0"),
        ("Renta del local", "Renta", "29000", "0.16"),
    ),
}
CLINICA = {
    "name": "Clínica Dental Sonríe",
    "business_type": "services",
    "tax_id": "CDS190227QX8",
    "opening": "140000",
    "incomes": (
        ("Consultas y limpiezas", "Servicios", "98000"),
        ("Ortodoncia", "Servicios", "126000"),
    ),
    "expenses": (
        ("Material dental", "Inventario", "41760", "0.16"),
        ("Nómina quincenal", "Nómina", "62000", "0"),
        ("Renta del consultorio", "Renta", "20880", "0.16"),
    ),
}
# Lo que un agente encontró en el banco de la clínica y dejó por aprobar.
PROPUESTAS = (
    ("Cargo recurrente de laboratorio dental", "Inventario", "8700", "Cargo mensual del laboratorio; coincide con los tres meses anteriores."),
    ("Mantenimiento del compresor", "Otros", "3480", "Transferencia a un proveedor nuevo; falta la factura."),
    ("Publicidad en redes", "Marketing", "2900", "Cargo con tarjeta; no hay gasto registrado ese día."),
)  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description="Cartera de un despacho para la demo")
    parser.add_argument("--url", default="http://localhost:8000", help="ARCA base URL")
    parser.add_argument("--password", default="demodespacho2026")
    parser.add_argument("--contador", default="C.P. Demo", help="Nombre del contador")
    parser.add_argument("--despacho", default="Despacho Contable del Valle")
    args = parser.parse_args()

    # El correo lleva la hora para que dos ensayos del mismo día no choquen.
    stamp = datetime.now().strftime("%m%d%H%M")
    contador_email = f"contador{stamp}@atlas.mx"
    duena_email = f"duena{stamp}@atlas.mx"
    http = httpx.Client(base_url=f"{args.url.rstrip('/')}/api", timeout=60)

    def call(method: str, path: str, headers: dict, **kwargs):
        response = http.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            sys.exit(f"{method} {path}: {response.status_code} {response.text}")
        return response.json()

    def post(path: str, payload: dict, headers: dict):
        return call("POST", path, headers, json=payload)

    def session(auth: dict, organization_id: str) -> dict:
        return {
            "Authorization": f"Bearer {auth['access_token']}",
            "X-Organization-ID": organization_id,
        }

    today = date.today()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    year, month = last_month_end.year, last_month_end.month

    def last_month(day: int) -> str:
        return date(year, month, day).isoformat()

    def operate(headers: dict, profile: dict) -> dict:
        """Un mes anterior creíble: ventas cobradas y gastos pagados desde el banco."""
        bank = post(
            "/accounts",
            {"name": "BBVA Empresarial", "type": "BANK",
             "opening_balance": profile["opening"], "institution": "BBVA"},
            headers,
        )
        income = {c["name"]: c for c in call("GET", "/categories", headers, params={"kind": "INCOME"})}
        expense = {c["name"]: c for c in call("GET", "/categories", headers, params={"kind": "EXPENSE"})}
        for day, (description, category, amount) in zip((9, 23), profile["incomes"], strict=True):
            post("/income", {
                "date": last_month(day),
                "description": description,
                "amount": amount,
                "tax_rate": "0.16",
                "category_id": income[category]["id"],
                "financial_account_id": bank["id"],
                "status": "PAID",
            }, headers)
        for day, (description, category, amount, tax_rate) in zip((5, 14, 20), profile["expenses"], strict=True):
            post("/expenses", {
                "date": last_month(day),
                "description": description,
                "amount": amount,
                "tax_rate": tax_rate,
                "category_id": expense[category]["id"],
                "financial_account_id": bank["id"],
                "status": "PAID",
            }, headers)
        return expense

    def close_last_month(headers: dict) -> None:
        post("/periods/close", {"year": year, "month": month}, headers)

    def register(email: str, name: str, business: str, business_type: str) -> dict:
        return post("/auth/register", {
            "email": email,
            "password": args.password,
            "name": name,
            "business_name": business,
            "business_type": business_type,
            "initial_cash": "5000",
        }, {})

    def new_company(auth: dict, profile: dict) -> dict:
        organization = post("/organizations", {
            "business_name": profile["name"],
            "business_type": profile["business_type"],
            "tax_id": profile["tax_id"],
            "initial_cash": "5000",
        }, {"Authorization": f"Bearer {auth['access_token']}"})
        return session(auth, organization["id"])

    # --- A · El despacho: la casa del contador, al corriente ---
    contador = register(contador_email, args.contador, args.despacho, "services")
    despacho = session(contador, contador["organization"]["id"])
    call("PATCH", "/organizations/current", despacho, json={"tax_id": "DCV150604MN2"})
    operate(despacho, DESPACHO)
    close_last_month(despacho)

    # --- B · Ferretería: operó el mes pasado y nadie lo ha cerrado ---
    ferreteria = new_company(contador, FERRETERIA)
    operate(ferreteria, FERRETERIA)

    # --- C · Restaurante: mes cerrado, pero le debe a un proveedor desde hace días ---
    restaurante = new_company(contador, RESTAURANTE)
    categorias = operate(restaurante, RESTAURANTE)
    proveedor = post("/vendors", {"name": "Carnes Selectas del Bajío"}, restaurante)
    # La cuenta por pagar se registra ANTES de cerrar el mes: su fecha de
    # registro puede caer en el mes anterior y un mes cerrado la rechazaría.
    post("/payables", {
        "vendor_id": proveedor["id"],
        "description": "Factura de cárnicos",
        "amount": "38400",
        "tax_rate": "0",
        "date": (today - timedelta(days=40)).isoformat(),
        "due_date": (today - timedelta(days=10)).isoformat(),
        "category_id": categorias["Inventario"]["id"],
    }, restaurante)
    close_last_month(restaurante)

    # --- D · Clínica: la dueña ya usaba ARCA e invita a su contador ---
    duena = register(duena_email, "Dra. Sofía Rangel", CLINICA["name"], CLINICA["business_type"])
    clinica = session(duena, duena["organization"]["id"])
    call("PATCH", "/organizations/current", clinica, json={"tax_id": CLINICA["tax_id"]})
    categorias = operate(clinica, CLINICA)
    close_last_month(clinica)
    post("/organizations/current/members", {
        "email": contador_email,
        "name": args.contador,
        "role": "ACCOUNTANT",
        "password": args.password,
    }, clinica)
    llave = post("/agent-keys", {"name": "Agente de conciliación", "scopes": "READ,PROPOSE"}, clinica)
    for description, category, amount, summary in PROPUESTAS:
        resultado = post("/agent/invoke", {
            "tool": "propose_expense",
            "arguments": {
                "date": today.isoformat(),
                "description": description,
                "amount": amount,
                "category_id": categorias[category]["id"],
                "summary": summary,
            },
        }, {"Authorization": f"Bearer {llave['token']}"})
        if not resultado.get("ok"):
            sys.exit(f"El agente no pudo proponer: {resultado}")

    cartera = call("GET", "/portfolio", {"Authorization": f"Bearer {contador['access_token']}"})

    print("\n╭─ Cartera lista ────────────────────────────────────────")
    print(f"│ URL        {args.url}")
    print(f"│ Contador   {contador_email}")
    print(f"│ Dueña (D)  {duena_email}")
    print(f"│ Contraseña {args.password}")
    print("│")
    for item in cartera["items"]:
        motivos = "; ".join(item["reasons"]) or "sin pendientes"
        print(f"│ {item['status']:<6} {item['name']:<28} {item['role']:<10} {motivos}")
    print("╰────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
