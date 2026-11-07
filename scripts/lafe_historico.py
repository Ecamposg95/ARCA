"""Carga el histórico de análisis de una empresa desde sus Excel.

Mismo cargador que `POST /api/admin/historical-loads`; corre con la sesión de
la app (DATABASE_URL), así que se ejecuta donde vive la base:

    python scripts/lafe_historico.py --org "Laboratorios La Fe" \
        --toronja ventas.xls --control-general CONTROL_GENERAL.xlsx \
        --reconstruccion reconstruccion.xlsx --efectivo Control_Efectivo.xlsx --dry-run

Recargar un archivo reemplaza el periodo que trae; no duplica. Nunca toca el
libro contable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from scripts.lafe_apertura import SeedError, find_organization  # noqa: E402

FAMILIES = (("toronja", "--toronja"), ("control_general", "--control-general"), ("reconstruccion", "--reconstruccion"), ("efectivo", "--efectivo"))


def main(argv: list[str] | None = None, db: Session | None = None):
    parser = argparse.ArgumentParser(description="Carga del histórico de análisis")
    parser.add_argument("--org", required=True, help="Nombre o id de la empresa")
    for family, flag in FAMILIES:
        parser.add_argument(flag, dest=family, help=f"Archivo de {family.replace('_', ' ')}")
    parser.add_argument("--dry-run", action="store_true", help="Lee y reporta sin guardar")
    args = parser.parse_args(argv)

    files = {}
    for family, _flag in FAMILIES:
        path = getattr(args, family)
        if path:
            files[family] = (Path(path).name, Path(path).read_bytes())
    if not files:
        parser.error("indica al menos un archivo")

    from app.domains.analytics.loading import load_files
    from app.domains.analytics.points import HistoricalFormatError

    own_session = db is None
    if own_session:
        import app.models  # noqa: F401
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        organization = find_organization(db, args.org)
        report = load_files(db, organization.id, files, None, dry_run=args.dry_run)
    except (SeedError, HistoricalFormatError) as error:
        db.rollback()
        sys.exit(str(error))
    finally:
        if own_session:
            db.close()

    print(f"{'[dry-run] ' if report.dry_run else ''}Histórico de {organization.name}:")
    for load in report.loads:
        print(f"  {load['family']:16} {load['period_from']} → {load['period_to']}  {load['rows']:>6} puntos  ({load['source']})")
    if report.unresolved_units:
        print("  Unidades sin resolver (agrega alias en Configuración › Unidades): " + ", ".join(report.unresolved_units))
    if report.unresolved_entities:
        print("  Contribuyentes sin resolver: " + ", ".join(report.unresolved_entities))
    return report


if __name__ == "__main__":
    main()
