"""Modelos SQLAlchemy de ARCA.

Importar aquí cada módulo de modelos: Base.metadata solo conoce las tablas
cuyos módulos fueron importados (crítico para create_all en tests y para
autogenerate de Alembic).
"""

from app.models.accounting import Account, JournalEntry, JournalEntryLine  # noqa: F401
from app.models.agent import AgentActionLog, AgentKey, AgentProposal  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.contact import Customer, Vendor  # noqa: F401
from app.models.expense import Expense  # noqa: F401
from app.models.financial_account import FinancialAccount  # noqa: F401
from app.models.fixed_asset import FixedAsset  # noqa: F401
from app.models.income import Income  # noqa: F401
from app.models.loan import Loan, LoanPayment  # noqa: F401
from app.models.organization import Organization, OrganizationMember  # noqa: F401
from app.models.payable import Payable  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.receivable import Receivable  # noqa: F401
from app.models.transaction import FinancialTransaction  # noqa: F401
from app.models.user import User  # noqa: F401

