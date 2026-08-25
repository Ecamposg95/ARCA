from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import AgentKey
from app.models.organization import ROLE_ADMIN, ROLE_OWNER
from app.models.user import User
from app.security.agent import generate_key
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(
    prefix="/agent-keys",
    tags=["agent-keys"],
    dependencies=[Depends(require_role((ROLE_OWNER, ROLE_ADMIN)))],
)


class AgentKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: Literal["READ", "READ,PROPOSE"] = "READ"


class AgentKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    key_prefix: str
    scopes: str
    active: bool
    last_used_at: datetime | None
    created_at: datetime


class AgentKeyCreated(AgentKeyRead):
    token: str  # SOLO en la respuesta de creación; jamás se vuelve a mostrar


@router.get("", response_model=list[AgentKeyRead])
def list_keys(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    keys = (
        db.query(AgentKey)
        .filter(AgentKey.organization_id == org_id)
        .order_by(AgentKey.created_at.desc())
        .all()
    )
    return [AgentKeyRead.model_validate(key) for key in keys]


@router.post("", response_model=AgentKeyCreated, status_code=201)
def create_key(
    payload: AgentKeyCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    token, prefix, digest = generate_key()
    key = AgentKey(
        organization_id=org_id,
        name=payload.name.strip(),
        key_prefix=prefix,
        key_hash=digest,
        scopes=payload.scopes,
        created_by=user.id,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return AgentKeyCreated(**AgentKeyRead.model_validate(key).model_dump(), token=token)


@router.delete("/{key_id}", response_model=AgentKeyRead)
def revoke_key(
    key_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    key = (
        db.query(AgentKey)
        .filter(AgentKey.id == key_id, AgentKey.organization_id == org_id)
        .first()
    )
    if key is None:
        raise HTTPException(status_code=404, detail="La llave no existe.")
    key.active = False
    db.commit()
    db.refresh(key)
    return AgentKeyRead.model_validate(key)
