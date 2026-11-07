"""Carga del histórico (sólo el dueño de la empresa) y series de análisis."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.analytics.loading import LOADERS, load_files
from app.domains.analytics.points import HistoricalFormatError
from app.domains.analytics.schemas import AnalyticsSeries, HistoricalLoadRead, HistoricalLoadReport
from app.domains.analytics.series import series
from app.models.historical import HistoricalLoad
from app.models.organization import ACCOUNTING_ROLES, ROLE_OWNER
from app.models.user import User
from app.security.deps import get_current_membership, get_current_org_id, get_current_user, require_role

router = APIRouter(tags=["analytics"])

MAX_FILE_BYTES = 40 * 1024 * 1024


def _read(upload: UploadFile | None) -> tuple[str, bytes] | None:
    if upload is None or not upload.filename:
        return None
    content = upload.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail=f"{upload.filename} pesa más de 40 MB")
    return upload.filename, content


@router.post("/admin/historical-loads", response_model=HistoricalLoadReport, status_code=201)
def upload_historical(
    toronja: UploadFile | None = File(default=None),
    control_general: UploadFile | None = File(default=None),
    reconstruccion: UploadFile | None = File(default=None),
    efectivo: UploadFile | None = File(default=None),
    dry_run: bool = Form(default=False),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role((ROLE_OWNER,))),
):
    uploads = {"toronja": toronja, "control_general": control_general, "reconstruccion": reconstruccion, "efectivo": efectivo}
    files = {family: read for family, upload in uploads.items() if (read := _read(upload)) is not None}
    if not files:
        raise HTTPException(status_code=400, detail="Sube al menos un archivo")
    assert set(files) <= set(LOADERS)
    try:
        report = load_files(db, org_id, files, user.id, dry_run=dry_run)
    except HistoricalFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HistoricalLoadReport(
        loads=report.loads,
        unresolved_units=report.unresolved_units,
        unresolved_entities=report.unresolved_entities,
        dry_run=report.dry_run,
    )


@router.get("/admin/historical-loads", response_model=list[HistoricalLoadRead])
def list_historical_loads(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(ACCOUNTING_ROLES)),
):
    return (
        db.query(HistoricalLoad)
        .filter(HistoricalLoad.organization_id == org_id)
        .order_by(HistoricalLoad.loaded_at.desc())
        .all()
    )


@router.get("/analytics/series", response_model=AnalyticsSeries)
def get_series(
    dataset: str = Query(default="sales"),
    metric: str = Query(default="net_sales"),
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    grain: str = Query(default="month", pattern="^(day|month)$"),
    business_unit_id: str | None = Query(default=None),
    fiscal_entity_id: str | None = Query(default=None),
    compare: str | None = Query(default=None, pattern="^previous_year$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(get_current_membership),  # todos los roles: Inicio es el mismo para todos
):
    try:
        return series(
            db,
            org_id,
            dataset=dataset,
            metric=metric,
            start=start,
            end=end,
            grain=grain,
            business_unit_id=business_unit_id or None,
            fiscal_entity_id=fiscal_entity_id or None,
            compare=compare,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
