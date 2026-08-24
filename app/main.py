"""ARCA — Financial Operating System (Atlas Tech).

App FastAPI única: API bajo /api/*, SPA React servida por catch-all (registrado al final).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("arca")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ARCA API",
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        # Errores de dominio (reglas financieras) llegan como ValueError con mensaje humano.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_request: Request, exc: IntegrityError):
        logger.warning("integrity_error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content={"detail": "La operación entra en conflicto con datos existentes."},
        )

    @app.get("/api/health", include_in_schema=False)
    def health():
        return {"status": "ok", "service": "arca", "environment": settings.env, "version": app.version}

    @app.get("/api/health/deep", include_in_schema=False)
    def health_deep():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception:  # noqa: BLE001 - el healthcheck no debe filtrar detalles
            logger.exception("health_deep: fallo de base de datos")
            db_status = "error"
        status = "ok" if db_status == "ok" else "degraded"
        return {"status": status, "database": db_status, "environment": settings.env}

    _register_routers(app)
    _mount_frontend(app)

    logger.info("ARCA iniciada (env=%s)", settings.env)
    return app


def _register_routers(app: FastAPI) -> None:
    # Los routers se agregan conforme avanza el plan (dominios bajo app/domains/).
    from app.routers import api_router

    app.include_router(api_router, prefix="/api")


def _mount_frontend(app: FastAPI) -> None:
    """Sirve la SPA construida. El catch-all se registra al final, después de todo /api."""
    if not FRONTEND_DIST.exists():
        return

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = FRONTEND_DIST / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_catch_all(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Recurso no encontrado."})
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


app = create_app()
