from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.agent_team import service
from app.security.deps import get_current_org_id

router = APIRouter(prefix="/agent-team", tags=["agent-team"])


@router.get("")
def roster(org_id: str = Depends(get_current_org_id)):
    """Los cinco agentes con su pregunta. El brief se pide por agente."""
    return {"items": list(service.AGENTS), "total": len(service.AGENTS), "limit": 5, "offset": 0}


@router.get("/{agent_id}/brief")
def brief(
    agent_id: str,
    monthly_cost: Decimal = Query(default=Decimal("35000"), gt=0, le=Decimal("500000")),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    kwargs = {"monthly_cost": monthly_cost} if agent_id == "forecast" else {}
    try:
        return service.build_brief(db, org_id, agent_id, **kwargs)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
