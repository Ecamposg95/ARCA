"""Registro central de routers de dominio. Todos se montan bajo /api."""

from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.categories.router import router as categories_router
from app.domains.contacts.router import customers_router, vendors_router
from app.domains.expenses.router import router as expenses_router
from app.domains.financial_accounts.router import router as financial_accounts_router
from app.domains.income.router import router as income_router
from app.domains.organizations.router import router as organizations_router
from app.domains.transactions.router import router as transactions_router
from app.domains.receivables.router import router as receivables_router
from app.domains.payables.router import router as payables_router
from app.domains.accounting.router import router as accounting_router
from app.domains.agent_api.router import router as agent_api_router
from app.domains.agent_keys.router import router as agent_keys_router
from app.domains.proposals.router import router as proposals_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.reports.router import router as reports_router
from app.domains.fixed_assets.router import router as fixed_assets_router
from app.domains.loans.router import router as loans_router
from app.domains.projects.router import router as projects_router
from app.domains.periods.router import router as periods_router
from app.domains.agent_team.router import router as agent_team_router
from app.domains.recurring.router import router as recurring_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(organizations_router)
api_router.include_router(financial_accounts_router)
api_router.include_router(categories_router)
api_router.include_router(customers_router)
api_router.include_router(vendors_router)
api_router.include_router(income_router)
api_router.include_router(expenses_router)
api_router.include_router(transactions_router)
api_router.include_router(receivables_router)
api_router.include_router(payables_router)
api_router.include_router(accounting_router)
api_router.include_router(agent_api_router)
api_router.include_router(agent_keys_router)
api_router.include_router(proposals_router)
api_router.include_router(dashboard_router)
api_router.include_router(reports_router)
api_router.include_router(fixed_assets_router)
api_router.include_router(loans_router)
api_router.include_router(projects_router)
api_router.include_router(periods_router)
api_router.include_router(agent_team_router)
api_router.include_router(recurring_router)
