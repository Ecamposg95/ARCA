"""Apertura provisional de Laboratorios La Fe al corte del 1-nov-2026.

Fija la fecha de corte (PROVISIONAL), da de alta los bancos y el procesador que
faltan en $0 provisional y lleva la Caja central a la única cifra confirmada
($27,407.00, control de efectivo al 31-oct). Las cajas de sucursal quedan en $0
provisional. No inventa cifras: lo que no se sabe queda en cero y "Pendiente";
se corrige desde Configuración › Apertura cuando llegue el documento.

Préstamos y activos fijos NO se siembran: su saldo al corte no está confirmado.

Usa la sesión de la app (DATABASE_URL), así que corre donde vive la base:

    python scripts/lafe_apertura.py --org "Laboratorios La Fe" --dry-run
    python scripts/lafe_apertura.py --org <organization_id>

Idempotente: correrlo dos veces no cambia nada. No pisa lo que alguien ya revisó
(una cuenta con estado de apertura) salvo la Caja central, y ésa sólo si sigue
provisional o sin revisar.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

CUTOFF = date(2026, 11, 1)
REASON = "Apertura de La Fe al corte del 1-nov-2026"
CAJA_CENTRAL = ("Caja central", Decimal("27407.00"), "CONFIRMED", "Control de efectivo al 31-oct-2026")
BRANCH_NOTE = "Pendiente: arqueo al 31-oct"

# (nombre, tipo, institución, nota). Todas en $0 provisional.
CUENTAS = (
    ("Santander PyME (Ale)", "BANK", "Santander", "Pendiente: estado de cuenta al 31-oct"),
    ("Bancomer PyME (Liza)", "BANK", "BBVA Bancomer", "Pendiente: estado de cuenta al 31-oct"),
    ("Santander Teresita (nómina)", "BANK", "Santander", "Pendiente: estado de cuenta al 31-oct"),
    ("NetPay", "PROCESSOR", "NetPay", "Pendiente: reporte de liquidación"),
)


class SeedError(RuntimeError):
    pass


def find_organization(db: Session, ref: str):
    from app.models.organization import Organization

    organization = db.get(Organization, ref)
    if organization is not None:
        return organization
    matches = db.query(Organization).filter(func.lower(Organization.name) == ref.strip().lower()).all()
    if not matches:
        raise SeedError(f"No existe la empresa {ref!r}.")
    if len(matches) > 1:
        ids = ", ".join(match.id for match in matches)
        raise SeedError(f"Hay varias empresas llamadas {ref!r}; usa el id: {ids}")
    return matches[0]


def run(db: Session, org_ref: str, dry_run: bool = False) -> list[str]:
    """Aplica la apertura y devuelve lo que hizo. Hace commit salvo en `dry_run` (rollback)."""
    from app.domains.financial_accounts.service import create_financial_account
    from app.domains.opening import service as opening
    from app.models.financial_account import FinancialAccount
    from app.services.change_log import change_source

    log: list[str] = []
    organization = find_organization(db, org_ref)
    org_id = organization.id

    def by_name() -> dict[str, FinancialAccount]:
        rows = (
            db.query(FinancialAccount)
            .filter(FinancialAccount.organization_id == org_id, FinancialAccount.deleted_at.is_(None))
            .all()
        )
        return {account.name.strip().lower(): account for account in rows}

    def settle(account: FinancialAccount, target: Decimal, status: str, note: str) -> None:
        current = (Decimal(account.opening_balance or 0), account.opening_status, account.opening_note)
        if current == (target, status, note):
            log.append(f"  = {account.name}: ${target:,.2f} {status}")
            return
        opening.adjust_account_opening(
            db, org_id, account.id, target=target, reason=REASON, status=status, note=note
        )
        log.append(f"  ~ {account.name}: ${current[0]:,.2f} → ${target:,.2f} {status} ({note})")

    with change_source("system"):
        # --- Fecha de corte ---
        if organization.opening_date is None:
            opening.update_settings(
                db, org_id, changes={"opening_date": CUTOFF, "opening_status": "PROVISIONAL"}, user_id=None
            )
            log.append(f"  + fecha de corte {CUTOFF:%d/%m/%Y} PROVISIONAL")
        elif organization.opening_date != CUTOFF:
            raise SeedError(
                f"{organization.name} ya tiene fecha de corte {organization.opening_date:%d/%m/%Y}; no la muevo."
            )
        else:
            log.append(f"  = fecha de corte {CUTOFF:%d/%m/%Y} {organization.opening_status}")

        # --- Bancos y procesador ($0 provisional) ---
        accounts = by_name()
        for name, kind, institution, note in CUENTAS:
            account = accounts.get(name.lower())
            if account is None:
                account = create_financial_account(
                    db, org_id, name=name, account_type=kind, opening_balance=Decimal("0"), institution=institution
                )
                log.append(f"  + {name} ({kind})")
            if account.opening_status is None:
                settle(account, Decimal("0.00"), "PROVISIONAL", note)
            else:
                log.append(f"  = {name}: ya revisada ({account.opening_status}); no la toco")

        # --- Caja central: la única cifra confirmada ---
        name, target, status, note = CAJA_CENTRAL
        accounts = by_name()
        central = accounts.get(name.lower())
        if central is None:
            central = create_financial_account(db, org_id, name=name, account_type="CASH")
            log.append(f"  + {name}")
        if central.opening_status == "CONFIRMED" and Decimal(central.opening_balance) != target:
            log.append(
                f"  ! {name} ya está confirmada en ${Decimal(central.opening_balance):,.2f}; no la toco"
            )
        else:
            settle(central, target, status, note)

        # --- Cajas de sucursal: $0 provisional, sólo si nadie las revisó ---
        for account in accounts.values():
            if account.type != "CASH" or account.id == central.id or account.opening_status is not None:
                continue
            if Decimal(account.opening_balance or 0) != 0:
                log.append(f"  ! {account.name} trae saldo inicial ${account.opening_balance:,.2f}; no la toco")
                continue
            settle(account, Decimal("0.00"), "PROVISIONAL", BRANCH_NOTE)

    if dry_run:
        db.rollback()
        log.append("Simulación: no se guardó nada.")
    else:
        db.commit()
        log.append("Listo.")
    return log


def main(argv: list[str] | None = None, db: Session | None = None) -> list[str]:
    parser = argparse.ArgumentParser(description="Apertura provisional de La Fe al 1-nov-2026")
    parser.add_argument("--org", required=True, help="Nombre o id de la empresa")
    parser.add_argument("--dry-run", action="store_true", help="Muestra lo que haría sin guardar")
    args = parser.parse_args(argv)

    own_session = db is None
    if own_session:
        import app.models  # noqa: F401  # registra todas las tablas
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        log = run(db, args.org, dry_run=args.dry_run)
    except SeedError as error:
        db.rollback()
        sys.exit(str(error))
    finally:
        if own_session:
            db.close()
    for line in log:
        print(line)
    return log


if __name__ == "__main__":
    main()
