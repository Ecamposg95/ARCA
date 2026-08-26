from datetime import date as date_type
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.reports import service
from app.domains.reports.export import to_csv
from app.security.deps import get_current_org_id

router = APIRouter(prefix="/reports", tags=["reports"])


def _default_month_range() -> tuple[date_type, date_type]:
    today = date.today()
    return today.replace(day=1), today


@router.get("/profit-loss")
def profit_loss(
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    default_start, default_end = _default_month_range()
    return service.profit_loss(db, org_id, start or default_start, end or default_end)


@router.get("/balance-sheet")
def balance_sheet(
    as_of: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.balance_sheet(db, org_id, as_of or date.today())


@router.get("/cash-flow")
def cash_flow(
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    default_start, default_end = _default_month_range()
    return service.cash_flow(db, org_id, start or default_start, end or default_end)


@router.get("/iva")
def vat(
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    default_start, default_end = _default_month_range()
    return service.vat_report(db, org_id, start or default_start, end or default_end)


@router.get("/cash-projection")
def cash_projection(
    days: int = Query(default=90, ge=7, le=365),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.cash_projection(db, org_id, days)


@router.get("/aging")
def aging(
    kind: str = Query(default="receivable", pattern="^(receivable|payable)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.aging_report(db, org_id, kind)


@router.get("/net-worth")
def net_worth(
    months: int = Query(default=12, ge=2, le=36),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.net_worth(db, org_id, months)


@router.get("/{report}/csv")
def export_csv(
    report: str,
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Descarga del reporte en CSV: lo que se le manda al contador."""
    default_start, default_end = _default_month_range()
    start = start or default_start
    end = end or default_end

    if report == "profit-loss":
        data = service.profit_loss(db, org_id, start, end)
        rows = [["INGRESOS", "", ""]]
        rows += [[line["code"], line["name"], line["amount"]] for line in data["revenue"]]
        rows.append(["", "Total de ingresos", data["total_revenue"]])
        rows.append(["GASTOS", "", ""])
        rows += [[line["code"], line["name"], line["amount"]] for line in data["expenses"]]
        rows.append(["", "Total de gastos", data["total_expenses"]])
        rows.append(["", "Resultado del periodo", data["net_profit"]])
        headers = ["Cuenta", "Concepto", "Importe"]
        name = f"estado-de-resultados-{start}-a-{end}"

    elif report == "balance-sheet":
        data = service.balance_sheet(db, org_id, end)
        rows = [["ACTIVO", "", ""]]
        rows += [[line["code"], line["name"], line["amount"]] for line in data["assets"]]
        rows.append(["", "Total de activo", data["total_assets"]])
        rows.append(["PASIVO", "", ""])
        rows += [[line["code"], line["name"], line["amount"]] for line in data["liabilities"]]
        rows.append(["", "Total de pasivo", data["total_liabilities"]])
        rows.append(["CAPITAL", "", ""])
        rows += [[line["code"], line["name"], line["amount"]] for line in data["equity"]]
        rows.append(["", "Total de capital", data["total_equity"]])
        headers = ["Cuenta", "Concepto", "Importe"]
        name = f"balance-general-{end}"

    elif report == "aging":
        data = service.aging_report(db, org_id, "receivable")
        headers = ["Cliente", *data["buckets"], "Total"]
        rows = [
            [c["name"], *[c.get(bucket, 0) for bucket in data["buckets"]], c["total"]]
            for c in data["contacts"]
        ]
        rows.append(["Total", *[data["totals"][b] for b in data["buckets"]], data["total"]])
        name = f"antiguedad-cartera-{end}"

    elif report == "trial-balance":
        from app.services.accounting.engine import trial_balance

        rows = [
            [row["code"], row["name"], row["debit"], row["credit"]]
            for row in trial_balance(db, org_id, end)
        ]
        headers = ["Cuenta", "Concepto", "Cargos", "Abonos"]
        name = f"balanza-de-comprobacion-{end}"

    else:
        raise HTTPException(status_code=404, detail="Ese reporte no se puede exportar.")

    return Response(
        content=to_csv(headers, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )
