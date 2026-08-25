"""Plan B del acto agéntico: la misma propuesta, sin el modelo en medio.

Si en el foro falla la red, el modelo o el cliente MCP, este script hace
exactamente la llamada que haría el agente —`POST /api/agent/invoke` con la
llave de agente— y deja la propuesta en la bandeja. El resto del acto (revisar,
aprobar, ver nacer la póliza) sigue siendo en vivo y es lo que importa.

    python scripts/demo_plan_b.py --url https://... --key ak_...

No inventa nada que el agente no pudiera hacer: usa la misma llave, el mismo
endpoint y los mismos permisos. Lo único que se pierde es el modelo eligiendo
la herramienta.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import httpx

CONCEPTO = "Suscripción anual de Figma"
MONTO = "18560"
RESUMEN = "Suscripción anual de Figma, pagada con la tarjeta AMEX"


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan B del acto agéntico")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--key", required=True, help="Llave de agente (ak_...)")
    args = parser.parse_args()

    client = httpx.Client(
        base_url=f"{args.url.rstrip('/')}/api",
        headers={"Authorization": f"Bearer {args.key}"},
        timeout=30,
    )

    def invoke(tool: str, arguments: dict) -> dict:
        response = client.post("/agent/invoke", json={"tool": tool, "arguments": arguments})
        if response.status_code >= 400:
            sys.exit(f"ARCA rechazó '{tool}': {response.status_code} {response.text}")
        return response.json()["result"]

    # El agente primero lee: nunca propone a ciegas.
    resumen = invoke("dashboard_summary", {})
    print(f"Leyó el tablero:  disponible {resumen['cash']} · deuda {resumen['card_debt']}")

    categorias = invoke("list_categories", {})
    items = categorias["items"] if isinstance(categorias, dict) else categorias
    software = next(c for c in items if c["name"] == "Software")

    cuentas = invoke("list_accounts", {})
    cuentas = cuentas["items"] if isinstance(cuentas, dict) else cuentas
    tarjeta = next(c for c in cuentas if c["type"] == "CREDIT_CARD")

    # Pagado con la tarjeta: al aprobarse nace la póliza y la deuda sube.
    propuesta = invoke(
        "propose_expense",
        {
            "summary": RESUMEN,
            "date": date.today().isoformat(),
            "description": CONCEPTO,
            "amount": MONTO,
            "tax_rate": "0.16",
            "category_id": software["id"],
            "financial_account_id": tarjeta["id"],
            "status": "PAID",
        },
    )
    print(f"Propuso:          {propuesta['summary']}")
    print(f"Estado:           {propuesta['status']} — espera aprobación humana")
    print("\nAbre Propuestas en ARCA y apruébala en pantalla.")


if __name__ == "__main__":
    main()
