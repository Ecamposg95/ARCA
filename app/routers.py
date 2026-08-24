"""Registro central de routers de dominio. Todos se montan bajo /api."""

from fastapi import APIRouter

api_router = APIRouter()

# Los dominios se registran aquí conforme se implementan:
# from app.domains.auth.router import router as auth_router
# api_router.include_router(auth_router)
