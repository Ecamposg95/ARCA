"""Activos fijos: alta, depreciación mensual y baja.

La depreciación es en línea recta —(costo − valor de rescate) ÷ meses de vida—
porque es la que un dueño puede explicar y la que el SAT acepta por defecto. El
cálculo se hace por mes cumplido, nunca por fracción de día.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.fixed_asset import FixedAsset
from app.services.accounting.engine import _quantize
from app.services.accounting.rules import depreciation_entry, fixed_asset_purchase_entry
from app.services.transactions import account_ledger_code, record_transaction


def monthly_depreciation(asset: FixedAsset) -> Decimal:
    """Cuota mensual en línea recta. Cero si el activo no se deprecia."""
    depreciable = Decimal(asset.cost) - Decimal(asset.salvage_value)
    if depreciable <= 0 or asset.useful_life_months <= 0:
        return Decimal("0")
    return _quantize(depreciable / Decimal(asset.useful_life_months))


def book_value(asset: FixedAsset) -> Decimal:
    return Decimal(asset.cost) - Decimal(asset.accumulated_depreciation)


def remaining_to_depreciate(asset: FixedAsset) -> Decimal:
    """Lo que aún falta llevar a gasto, sin pasarse del valor de rescate."""
    depreciable = Decimal(asset.cost) - Decimal(asset.salvage_value)
    return max(depreciable - Decimal(asset.accumulated_depreciation), Decimal("0"))


def months_elapsed(start: date_type, until: date_type) -> int:
    """Meses cumplidos entre dos fechas. El mes de compra no se deprecia."""
    months = (until.year - start.year) * 12 + (until.month - start.month)
    return max(months, 0)


def create_asset(
    db: Session,
    organization_id: str,
    *,
    name: str,
    category: str,
    acquisition_date: date_type,
    cost: Decimal,
    useful_life_months: int,
    salvage_value: Decimal = Decimal("0"),
    tax_amount: Decimal = Decimal("0"),
    financial_account_id: str | None = None,
    vendor_id: str | None = None,
    notes: str | None = None,
    user_id: str | None = None,
) -> FixedAsset:
    cost = _quantize(Decimal(cost))
    salvage_value = _quantize(Decimal(salvage_value))
    tax_amount = _quantize(Decimal(tax_amount))

    if salvage_value >= cost:
        raise ValueError("El valor de rescate debe ser menor al costo.")

    asset = FixedAsset(
        organization_id=organization_id,
        name=name,
        category=category,
        acquisition_date=acquisition_date,
        cost=cost,
        tax_amount=tax_amount,
        salvage_value=salvage_value,
        useful_life_months=useful_life_months,
        financial_account_id=financial_account_id,
        vendor_id=vendor_id,
        notes=notes,
        created_by=user_id,
    )
    db.add(asset)
    db.flush()

    # Si se pagó, el dinero sale de una cuenta y la póliza lo refleja.
    if financial_account_id:
        record_transaction(
            db,
            organization_id=organization_id,
            financial_account_id=financial_account_id,
            transaction_type="EXPENSE",
            amount=cost + tax_amount,
            date=acquisition_date,
            description=f"Compra de activo: {name}",
            source_type="fixed_asset",
            source_id=asset.id,
            created_by=user_id,
        )
        cash_code = account_ledger_code(db, organization_id, financial_account_id)
    else:
        cash_code = None

    if cash_code:
        fixed_asset_purchase_entry(
            db,
            organization_id,
            description=f"Compra de activo: {name}",
            cost=cost,
            date=acquisition_date,
            source_id=asset.id,
            created_by=user_id,
            cash_account_code=cash_code,
            tax_amount=tax_amount,
        )

    db.commit()
    db.refresh(asset)
    return asset


def _period_end(year: int, month: int) -> date_type:
    return date_type(year, month, monthrange(year, month)[1])


def run_depreciation(
    db: Session,
    organization_id: str,
    year: int,
    month: int,
    user_id: str | None = None,
) -> dict:
    """Asienta la depreciación de un mes para todos los activos vigentes.

    Es idempotente: si el mes ya se corrió, no vuelve a asentar. Un mes contable
    no puede depreciarse dos veces sin que el patrimonio quede mal.
    """
    period_end = _period_end(year, month)
    period_key = f"{year:04d}-{month:02d}"

    # La depreciación se asienta al cierre del mes. Correrla antes pondría una
    # póliza con fecha futura, que no aparece en ningún reporte hasta que llegue
    # ese día: el activo se vería intacto y el gasto, perdido.
    if period_end > date_type.today():
        raise ValueError(
            f"El mes {period_key} todavía no termina. La depreciación se asienta al cierre."
        )

    assets = (
        db.query(FixedAsset)
        .filter(
            FixedAsset.organization_id == organization_id,
            FixedAsset.status == "ACTIVE",
        )
        .all()
    )

    already = {
        source_id
        for (source_id,) in db.query(JournalEntry.source_id).filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.source_type == "depreciation",
            JournalEntry.source_id.like(f"%:{period_key}"),
        )
    }

    posted: list[dict] = []
    skipped: list[dict] = []
    total = Decimal("0")

    for asset in assets:
        source_id = f"{asset.id}:{period_key}"
        if source_id in already:
            skipped.append({"asset_id": asset.id, "name": asset.name, "reason": "ya asentado"})
            continue
        if months_elapsed(asset.acquisition_date, period_end) < 1:
            skipped.append({"asset_id": asset.id, "name": asset.name, "reason": "aún no cumple un mes"})
            continue

        pending = remaining_to_depreciate(asset)
        if pending <= 0:
            skipped.append({"asset_id": asset.id, "name": asset.name, "reason": "totalmente depreciado"})
            continue

        # El último mes ajusta al remanente exacto: nunca se deprecia de más.
        amount = min(monthly_depreciation(asset), pending)
        if amount <= 0:
            continue

        depreciation_entry(
            db,
            organization_id,
            description=f"Depreciación {period_key} · {asset.name}",
            amount=amount,
            date=period_end,
            source_id=source_id,
            created_by=user_id,
        )
        asset.accumulated_depreciation = _quantize(
            Decimal(asset.accumulated_depreciation) + amount
        )
        total += amount
        posted.append({"asset_id": asset.id, "name": asset.name, "amount": amount})

    db.commit()
    return {"period": period_key, "posted": posted, "skipped": skipped, "total": total}


def dispose_asset(
    db: Session,
    organization_id: str,
    asset: FixedAsset,
    disposed_at: date_type,
    user_id: str | None = None,
) -> FixedAsset:
    """Da de baja el activo. No borra su historia: lo marca y deja de depreciar."""
    asset.status = "DISPOSED"
    asset.disposed_at = disposed_at
    asset.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(asset)
    return asset


def summary(db: Session, organization_id: str) -> dict:
    assets = (
        db.query(FixedAsset)
        .filter(
            FixedAsset.organization_id == organization_id,
            FixedAsset.status == "ACTIVE",
        )
        .all()
    )
    cost = sum((Decimal(a.cost) for a in assets), Decimal("0"))
    depreciated = sum((Decimal(a.accumulated_depreciation) for a in assets), Decimal("0"))
    return {
        "count": len(assets),
        "total_cost": cost,
        "accumulated_depreciation": depreciated,
        "book_value": cost - depreciated,
        "monthly_depreciation": sum((monthly_depreciation(a) for a in assets), Decimal("0")),
    }
