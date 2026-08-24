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
