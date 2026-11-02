"""Autorización por monto (spec 2026-11-02).

Lo que alcanza el umbral de la empresa no se registra: queda como
`AgentProposal` en la bandeja y sólo quien tiene facultad de autorizar lo
aprueba o rechaza. Este módulo es el ÚNICO lugar donde se evalúa el umbral,
el límite del auxiliar y la facultad; los routers de gasto, pago a proveedor y
traspaso lo llaman antes de ejecutar su service, y la bandeja lo consulta al
aprobar.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.agent import AgentActionLog, AgentProposal
from app.models.organization import ROLE_MEMBER, ROLE_OWNER, Organization, OrganizationMember
from app.models.user import User

ROLE_LABELS = {
    "OWNER": "dueño",
    "ADMIN": "administrador",
    "ACCOUNTANT": "contador",
    "MEMBER": "auxiliar",
    "VIEWER": "lector",
}

ORIGIN_PREFIX = "approval:"


class CaptureLimitExceeded(Exception):
    """El auxiliar intentó capturar más de lo que su límite permite (403)."""


class NotAnAuthorizer(Exception):
    """Quien intenta aprobar o rechazar no tiene facultad (403)."""


def money(amount: Decimal | str | int) -> str:
    return f"${Decimal(amount):,.2f}"


def can_authorize(membership: OrganizationMember) -> bool:
    """El dueño autoriza siempre; los demás, sólo con la facultad encendida."""
    return membership.role == ROLE_OWNER or bool(membership.can_authorize)


def reaches_threshold(organization: Organization, amount: Decimal) -> bool:
    threshold = organization.approval_threshold
    return threshold is not None and Decimal(amount) >= Decimal(threshold)


def requires_approval(
    db: Session, organization: Organization, membership: OrganizationMember, amount: Decimal
) -> bool:
    """¿Esta operación debe esperar en la bandeja en vez de registrarse?"""
    return reaches_threshold(organization, amount) and not can_authorize(membership)


def enforce_capture_limit(organization: Organization, membership: OrganizationMember, amount: Decimal) -> None:
    """El auxiliar no captura por encima de su límite; se evalúa ANTES del umbral."""
    limit = organization.member_capture_limit
    if membership.role == ROLE_MEMBER and limit is not None and Decimal(amount) > Decimal(limit):
        raise CaptureLimitExceeded("Ese monto necesita a un administrador.")


def submit_for_approval(
    db: Session,
    organization_id: str,
    user: User,
    membership: OrganizationMember,
    *,
    kind: str,
    payload: dict,
    summary: str,
) -> AgentProposal:
    """Deja la operación en la bandeja con quién la capturó y cuándo. Nada más."""
    now = datetime.now(timezone.utc)
    role = ROLE_LABELS.get(membership.role, membership.role.lower())
    proposal = AgentProposal(
        organization_id=organization_id,
        agent_key_id=None,
        kind=kind,
        payload=payload,
        summary=summary[:300],
        evidence=f"Capturado por {user.name} ({role}) el {now:%d/%m/%Y %H:%M} UTC.",
        origin=f"{ORIGIN_PREFIX}{user.id}:{uuid4().hex[:16]}",
        requested_by=user.id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    event_bus.publish("proposal.created", {"proposal_id": proposal.id, "organization_id": organization_id})
    return proposal


def audit_self_authorized(db: Session, organization_id: str, user_id: str, *, kind: str, amount: Decimal, summary: str) -> None:
    """Quien tiene facultad registra directo, pero queda huella de que fue él.

    Mismo registro que usan agentes y asistente; el service de la operación
    hace el commit (si la operación falla, la huella se va con ella).
    """
    db.add(
        AgentActionLog(
            organization_id=organization_id,
            agent_key_id=None,
            user_id=user_id,
            tool=f"self_authorized_{kind.lower()}",
            arguments={"amount": str(amount), "summary": summary[:300]},
            success=True,
        )
    )
    db.flush()


def gate(
    db: Session,
    *,
    membership: OrganizationMember,
    user: User,
    amount: Decimal,
    kind: str,
    payload: dict,
    summary: str,
) -> AgentProposal | None:
    """Límite del auxiliar → umbral → facultad. Devuelve la propuesta si la
    operación debe esperar; None si puede registrarse ya."""
    organization = db.get(Organization, membership.organization_id)
    enforce_capture_limit(organization, membership, amount)
    if not reaches_threshold(organization, amount):
        return None
    if can_authorize(membership):
        audit_self_authorized(db, organization.id, user.id, kind=kind, amount=amount, summary=summary)
        return None
    return submit_for_approval(
        db, organization.id, user, membership, kind=kind, payload=payload, summary=summary
    )


def authorizer_names(db: Session, organization_id: str) -> list[str]:
    """Para el aviso "se envió a autorización de ...": dueño y quienes tienen facultad."""
    rows = (
        db.query(User.name)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .filter(
            OrganizationMember.organization_id == organization_id,
            (OrganizationMember.role == ROLE_OWNER) | (OrganizationMember.can_authorize.is_(True)),
        )
        .order_by(OrganizationMember.created_at)
        .all()
    )
    return [name for (name,) in rows]


def pending_body(db: Session, proposal: AgentProposal) -> dict:
    """Cuerpo del 202: no devuelve la operación porque no existe todavía."""
    organization = db.get(Organization, proposal.organization_id)
    return {
        "pending_approval": True,
        "proposal_id": proposal.id,
        "detail": f"Se envió a autorización: supera el umbral de {money(organization.approval_threshold)}.",
        "authorizers": authorizer_names(db, proposal.organization_id),
    }


def is_approval(proposal: AgentProposal) -> bool:
    return (proposal.origin or "").startswith(ORIGIN_PREFIX)


def proposal_needs_authorizer(db: Session, proposal: AgentProposal) -> bool:
    """Las de autorización siempre; cualquier otra (agente, asistente) si su
    monto alcanza el umbral: aprobarla sin facultad sería la puerta trasera."""
    if is_approval(proposal):
        return True
    amount = (proposal.payload or {}).get("amount")
    if amount is None:
        return False
    organization = db.get(Organization, proposal.organization_id)
    try:
        return reaches_threshold(organization, Decimal(str(amount)))
    except ArithmeticError:
        return False


def ensure_can_review(db: Session, membership: OrganizationMember, proposal: AgentProposal) -> None:
    if proposal_needs_authorizer(db, proposal) and not can_authorize(membership):
        raise NotAnAuthorizer("Solo quien autoriza puede aprobar.")
