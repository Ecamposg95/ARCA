from decimal import Decimal

from sqlalchemy import JSON, Boolean, Column, Date, ForeignKey, Numeric, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, UUIDPKMixin


class Organization(Base, UUIDPKMixin, AuditMixin):
    __tablename__ = "organizations"

    name = Column(String(255), nullable=False)
    legal_name = Column(String(255), nullable=True)
    tax_id = Column(String(20), nullable=True)
    currency = Column(String(3), nullable=False, default="MXN")
    country = Column(String(2), nullable=False, default="MX")
    timezone = Column(String(64), nullable=False, default="America/Mexico_City")
    business_type = Column(String(50), nullable=True)
    # Tasa que propone el formulario; un negocio exento la deja en 0.
    default_tax_rate = Column(Numeric(5, 4), nullable=False, default=Decimal("0.16"))
    # Asistente sobre Claude: tope mensual en USD (null = AI_BUDGET_DEFAULT_USD) y apagador.
    ai_budget_usd = Column(Numeric(10, 2), nullable=True)
    ai_enabled = Column(Boolean, nullable=False, default=True)
    # Importación: {toronja: {bank_account_id, processor_account_id,
    # receivable_customer_id, income_category_id}}. Vacío hasta configurarse.
    import_settings = Column(JSON, nullable=False, default=dict)
    # Autorización por monto (spec 2026-11-02): lo que alcance el umbral va a la
    # bandeja antes de registrarse (null = nadie autoriza nada); el auxiliar
    # (MEMBER) no captura por encima de su límite (null = sin límite).
    approval_threshold = Column(Numeric(14, 2), nullable=True)
    member_capture_limit = Column(Numeric(14, 2), nullable=True)
    # Fecha de corte: el día en que la empresa empieza en ONE Finance. Todo
    # saldo de apertura (y cada ajuste posterior) va fechado aquí, no el día en
    # que se capturó. `opening_status` dice si la apertura ya se confirmó con
    # estados de cuenta (CONFIRMED) o sigue provisional (PROVISIONAL).
    opening_date = Column(Date, nullable=True)
    opening_status = Column(String(20), nullable=True)  # OPENING_STATUSES
    # Marca propia sobre ONE Finance (VALID_BRANDS): el backend sólo guarda la
    # clave; acento y logotipo viven en el front (`frontend/src/lib/brand.ts`).
    brand = Column(String(40), nullable=True)


# Marcas que el front sabe pintar. Agregar una aquí exige sus tokens y su logo allá.
VALID_BRANDS = ("lafe",)


# Estado de un saldo de apertura: provisional hasta que llega el estado de
# cuenta que lo respalda. Lo provisional vive contra la cuenta puente 3901.
OPENING_PROVISIONAL = "PROVISIONAL"
OPENING_CONFIRMED = "CONFIRMED"
OPENING_STATUSES = (OPENING_PROVISIONAL, OPENING_CONFIRMED)


ROLE_OWNER = "OWNER"
ROLE_ADMIN = "ADMIN"
ROLE_ACCOUNTANT = "ACCOUNTANT"
ROLE_MEMBER = "MEMBER"
ROLE_VIEWER = "VIEWER"
VALID_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_MEMBER, ROLE_VIEWER)

# Roles con acceso a la sección de Contabilidad (task pack §25)
ACCOUNTING_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_ACCOUNTANT)
# Roles que pueden registrar operaciones financieras
WRITE_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_MEMBER)


class OrganizationMember(Base, UUIDPKMixin, AuditMixin):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)

    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default=ROLE_MEMBER)
    # Facultad de autorizar lo que alcanza el umbral. El OWNER autoriza siempre,
    # diga lo que diga esta bandera: `services.approvals.can_authorize` decide.
    can_authorize = Column(Boolean, nullable=False, default=False)
