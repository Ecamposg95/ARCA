"""Registro central de routers de dominio. Todos se montan bajo /api."""

from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.categories.router import router as categories_router
from app.domains.financial_accounts.router import router as financial_accounts_router
from app.domains.organizations.router import router as organizations_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(organizations_router)
api_router.include_router(financial_accounts_router)
api_router.include_router(categories_router)
