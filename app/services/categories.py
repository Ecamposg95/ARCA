"""Categorías default por organización (task pack §13), mapeadas al catálogo contable."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.category import Category

# (name, kind, account_code)
DEFAULT_CATEGORIES = (
    ("Ventas", "INCOME", "4100"),
    ("Servicios", "INCOME", "4200"),
    ("Intereses", "INCOME", "4200"),
    ("Otros ingresos", "INCOME", "4100"),
    ("Nómina", "EXPENSE", "5200"),
    ("Renta", "EXPENSE", "5300"),
    ("Servicios", "EXPENSE", "5100"),
    ("Marketing", "EXPENSE", "5500"),
    ("Software", "EXPENSE", "5400"),
    ("Transporte", "EXPENSE", "5600"),
    ("Viáticos", "EXPENSE", "5600"),
    ("Inventario", "EXPENSE", "5100"),
    ("Honorarios", "EXPENSE", "5100"),
    ("Impuestos", "EXPENSE", "5700"),
    ("Equipo", "EXPENSE", "5100"),
    ("Otros", "EXPENSE", "5700"),
)


def seed_default_categories(db: Session, organization_id: str) -> None:
    """Idempotente por (org, kind, name). No hace commit."""
    existing = {
        (kind, name)
        for kind, name in db.query(Category.kind, Category.name)
        .filter(Category.organization_id == organization_id)
        .all()
    }
    for name, kind, account_code in DEFAULT_CATEGORIES:
        if (kind, name) in existing:
            continue
        db.add(
            Category(
                organization_id=organization_id,
                name=name,
                kind=kind,
                account_code=account_code,
                system=True,
            )
        )
    db.flush()
