from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.projects import service
from app.domains.projects.schemas import ProjectCreate, ProjectRead
from app.models.organization import WRITE_ROLES
from app.models.project import Project
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(
    status: str | None = Query(default=None, pattern="^(ACTIVE|CLOSED|CANCELLED)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    rows = service.list_with_profitability(db, org_id, status)
    # Lo no asignado también es información: dice cuánto del negocio no se mide.
    unassigned = service.profitability(db, org_id, None)
    return {
        "items": rows,
        "total": len(rows),
        "limit": len(rows),
        "offset": 0,
        "unassigned": unassigned,
    }


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    return service.create_project(
        db,
        org_id,
        name=payload.name,
        code=payload.code,
        customer_id=payload.customer_id,
        description=payload.description,
        budget=payload.budget,
        start_date=payload.start_date,
        end_date=payload.end_date,
        user_id=user.id,
    )


@router.post("/{project_id}/close", response_model=ProjectRead)
def close_project(
    project_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.organization_id == org_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="El proyecto no existe.")
    return service.close_project(db, project)
