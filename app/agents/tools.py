"""Catálogo de herramientas financieras para agentes.

Los handlers SOLO llaman services/queries existentes y devuelven JSON
serializable. Las herramientas propose_* crean AgentProposal — jamás
ejecutan la operación (eso lo hace un humano en la bandeja).

Este catálogo es la única superficie agéntica: CFO (A1), MCP (A2) e
Inbox (A3) lo reutilizan tal cual.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.domains.dashboard.service import summary as dashboard_summary_service
from app.domains.expenses.schemas import ExpenseCreate
from app.domains.income.schemas import IncomeCreate
from app.domains.payables.schemas import PayableCreate, PayableRead
from app.domains.receivables.schemas import ReceivableCreate, ReceivableRead
from app.domains.reports import service as reports
from app.models.agent import AgentProposal
from app.models.category import Category
from app.models.contact import Customer, Vendor
from app.models.expense import Expense
from app.models.financial_account import FinancialAccount
from app.models.income import Income
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.transaction import FinancialTransaction
from app.services.accounting.engine import trial_balance


class EmptyParams(BaseModel):
    pass


class PeriodParams(BaseModel):
    start: date_type | None = None
    end: date_type | None = None


class AsOfParams(BaseModel):
    as_of: date_type | None = None


class AgingParams(BaseModel):
    kind: Literal["receivable", "payable"] = "receivable"


class ProjectionParams(BaseModel):
    days: int = Field(default=90, ge=7, le=365)


class NetWorthParams(BaseModel):
    months: int = Field(default=12, ge=2, le=36)


class KindParams(BaseModel):
    kind: Literal["INCOME", "EXPENSE"] | None = None


class SearchParams(BaseModel):
    q: str | None = Field(default=None, max_length=100)


class StatusPeriodParams(BaseModel):
    status: Literal["PENDING", "PAID", "CANCELLED"] | None = None
    start: date_type | None = None
    end: date_type | None = None


class DebtStatusParams(BaseModel):
    status: Literal["OPEN", "PARTIAL", "PAID", "CANCELLED", "OVERDUE"] | None = None


class TransactionFilterParams(BaseModel):
    account_id: str | None = None
    start: date_type | None = None
    end: date_type | None = None


class ProposalExtra(BaseModel):
    summary: str = Field(min_length=1, max_length=300, description="Resumen humano de la propuesta")
    evidence: str | None = Field(default=None, max_length=2000, description="Contexto o evidencia")


class ProposeIncomeParams(IncomeCreate, ProposalExtra):
    pass


class ProposeExpenseParams(ExpenseCreate, ProposalExtra):
    pass


class ProposeReceivableParams(ReceivableCreate, ProposalExtra):
    pass


class ProposePayableParams(PayableCreate, ProposalExtra):
    pass


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date_type):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _rows(rows: list, columns: list[str]) -> list[dict]:
    return [{col: _json(getattr(row, col)) for col in columns} for row in rows]


# --- Handlers de lectura -------------------------------------------------


def _dashboard(db: Session, org_id: str, _params: EmptyParams):
    return _json(dashboard_summary_service(db, org_id))


def _profit_loss(db: Session, org_id: str, params: PeriodParams):
    start = params.start or date.today().replace(day=1)
    end = params.end or date.today()
    return _json(reports.profit_loss(db, org_id, start, end))


def _balance_sheet(db: Session, org_id: str, params: AsOfParams):
    return _json(reports.balance_sheet(db, org_id, params.as_of or date.today()))


def _aging(db: Session, org_id: str, params: AgingParams):
    return _json(reports.aging_report(db, org_id, params.kind))


def _cash_projection(db: Session, org_id: str, params: ProjectionParams):
    return _json(reports.cash_projection(db, org_id, params.days))


def _net_worth(db: Session, org_id: str, params: NetWorthParams):
    return _json(reports.net_worth(db, org_id, params.months))


def _cash_flow(db: Session, org_id: str, params: PeriodParams):
    start = params.start or date.today().replace(day=1)
    end = params.end or date.today()
    return _json(reports.cash_flow(db, org_id, start, end))


def _trial_balance(db: Session, org_id: str, _params: EmptyParams):
    return _json(trial_balance(db, org_id))


def _list_accounts(db: Session, org_id: str, _params: EmptyParams):
    rows = (
        db.query(FinancialAccount)
        .filter(FinancialAccount.organization_id == org_id, FinancialAccount.deleted_at.is_(None))
        .all()
    )
    return _rows(rows, ["id", "name", "type", "currency", "current_balance", "active"])


def _list_categories(db: Session, org_id: str, params: KindParams):
    query = db.query(Category).filter(Category.organization_id == org_id, Category.active.is_(True))
    if params.kind:
        query = query.filter(Category.kind == params.kind)
    return _rows(query.order_by(Category.kind, Category.name).all(), ["id", "name", "kind", "account_code"])


def _contact_lister(model):
    def _handler(db: Session, org_id: str, params: SearchParams):
        query = db.query(model).filter(model.organization_id == org_id, model.deleted_at.is_(None))
        if params.q:
            query = query.filter(model.name.ilike(f"%{params.q}%"))
        return _rows(query.order_by(model.name).limit(100).all(), ["id", "name", "email", "phone", "status"])

    return _handler


def _list_incomes(db: Session, org_id: str, params: StatusPeriodParams):
    query = db.query(Income).filter(Income.organization_id == org_id)
    if params.status:
        query = query.filter(Income.status == params.status)
    if params.start:
        query = query.filter(Income.date >= params.start)
    if params.end:
        query = query.filter(Income.date <= params.end)
    rows = query.order_by(Income.date.desc()).limit(200).all()
    return _rows(rows, ["id", "date", "description", "amount", "status", "customer_id", "category_id"])


def _list_expenses(db: Session, org_id: str, params: StatusPeriodParams):
    query = db.query(Expense).filter(Expense.organization_id == org_id)
    if params.status:
        query = query.filter(Expense.status == params.status)
    if params.start:
        query = query.filter(Expense.date >= params.start)
    if params.end:
        query = query.filter(Expense.date <= params.end)
    rows = query.order_by(Expense.date.desc()).limit(200).all()
    return _rows(rows, ["id", "date", "description", "amount", "status", "vendor_id", "category_id"])


def _debt_lister(model, read_schema):
    def _handler(db: Session, org_id: str, params: DebtStatusParams):
        query = db.query(model).filter(model.organization_id == org_id)
        if params.status == "OVERDUE":
            query = query.filter(model.status.in_(("OPEN", "PARTIAL")), model.due_date < date.today())
        elif params.status:
            query = query.filter(model.status == params.status)
        rows = query.order_by(model.due_date.asc()).limit(200).all()
        return [read_schema.model_validate(row).model_dump(mode="json") for row in rows]

    return _handler


def _list_transactions(db: Session, org_id: str, params: TransactionFilterParams):
    query = db.query(FinancialTransaction).filter(FinancialTransaction.organization_id == org_id)
    if params.account_id:
        query = query.filter(FinancialTransaction.financial_account_id == params.account_id)
    if params.start:
        query = query.filter(FinancialTransaction.date >= params.start)
    if params.end:
        query = query.filter(FinancialTransaction.date <= params.end)
    rows = query.order_by(FinancialTransaction.date.desc()).limit(200).all()
    return _rows(rows, ["id", "date", "description", "amount", "transaction_type", "financial_account_id", "status"])


# --- Handlers de propuesta ----------------------------------------------


def _proposer(kind: str, extra_fields: tuple[str, ...] = ("summary", "evidence")):
    def _handler(db: Session, org_id: str, params: BaseModel, agent_key_id: str):
        data = params.model_dump(mode="json")
        summary = data.pop("summary")
        evidence = data.pop("evidence", None)
        for field in extra_fields:
            data.pop(field, None)
        proposal = AgentProposal(
            organization_id=org_id,
            agent_key_id=agent_key_id,
            kind=kind,
            payload=data,
            summary=summary,
            evidence=evidence,
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        event_bus.publish("proposal.created", {"proposal_id": proposal.id, "organization_id": org_id})
        return {"proposal_id": proposal.id, "status": proposal.status, "summary": proposal.summary}

    return _handler


# --- Registro ------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params_model: type[BaseModel]
    scope: Literal["READ", "PROPOSE"]
    handler: Callable
    needs_agent_key: bool = False


TOOLS: dict[str, ToolSpec] = {
    tool.name: tool
    for tool in [
        ToolSpec("dashboard_summary", "Resumen ejecutivo: efectivo, ingresos/gastos del mes, por cobrar/pagar y series.", EmptyParams, "READ", _dashboard),
        ToolSpec("profit_loss", "Estado de resultados del periodo (default: mes actual).", PeriodParams, "READ", _profit_loss),
        ToolSpec("balance_sheet", "Balance general a una fecha (default: hoy).", AsOfParams, "READ", _balance_sheet),
        ToolSpec("cash_flow", "Flujo de efectivo del periodo (default: mes actual).", PeriodParams, "READ", _cash_flow),
        ToolSpec("trial_balance", "Balanza de comprobación por cuenta contable.", EmptyParams, "READ", _trial_balance),
        ToolSpec("aging_report", "Antigüedad de cartera por contraparte con tramos y días promedio (DSO).", AgingParams, "READ", _aging),
        ToolSpec("cash_projection", "Proyección de liquidez a N días con compromisos ya registrados; avisa el día del faltante.", ProjectionParams, "READ", _cash_projection),
        ToolSpec("net_worth", "Patrimonio neto: activos menos deudas, con evolución mensual.", NetWorthParams, "READ", _net_worth),
        ToolSpec("list_accounts", "Cuentas de dinero (caja, bancos) con saldos actuales.", EmptyParams, "READ", _list_accounts),
        ToolSpec("list_categories", "Categorías de ingreso/gasto con su cuenta contable.", KindParams, "READ", _list_categories),
        ToolSpec("list_customers", "Clientes de la organización (búsqueda por nombre).", SearchParams, "READ", _contact_lister(Customer)),
        ToolSpec("list_vendors", "Proveedores de la organización (búsqueda por nombre).", SearchParams, "READ", _contact_lister(Vendor)),
        ToolSpec("list_incomes", "Ingresos registrados, filtrables por estado y periodo.", StatusPeriodParams, "READ", _list_incomes),
        ToolSpec("list_expenses", "Gastos registrados, filtrables por estado y periodo.", StatusPeriodParams, "READ", _list_expenses),
        ToolSpec("list_receivables", "Cuentas por cobrar con saldos y estado (incl. OVERDUE).", DebtStatusParams, "READ", _debt_lister(Receivable, ReceivableRead)),
        ToolSpec("list_payables", "Cuentas por pagar con saldos y estado (incl. OVERDUE).", DebtStatusParams, "READ", _debt_lister(Payable, PayableRead)),
        ToolSpec("list_transactions", "Movimientos de dinero, filtrables por cuenta y periodo.", TransactionFilterParams, "READ", _list_transactions),
        ToolSpec("propose_income", "PROPONE un ingreso (queda pendiente de aprobación humana).", ProposeIncomeParams, "PROPOSE", _proposer("INCOME"), needs_agent_key=True),
        ToolSpec("propose_expense", "PROPONE un gasto (queda pendiente de aprobación humana).", ProposeExpenseParams, "PROPOSE", _proposer("EXPENSE"), needs_agent_key=True),
        ToolSpec("propose_receivable", "PROPONE una cuenta por cobrar (pendiente de aprobación).", ProposeReceivableParams, "PROPOSE", _proposer("RECEIVABLE"), needs_agent_key=True),
        ToolSpec("propose_payable", "PROPONE una cuenta por pagar (pendiente de aprobación).", ProposePayableParams, "PROPOSE", _proposer("PAYABLE"), needs_agent_key=True),
    ]
}
