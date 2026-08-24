"""Motor de base de datos y sesión.

pool_pre_ping siempre (patrón Atlas endurecido en producción).
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

_engine_kwargs: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update(pool_size=10, max_overflow=10, pool_recycle=1800, pool_timeout=30)

engine = create_engine(settings.database_url, **_engine_kwargs)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:

    @event.listens_for(engine, "connect")
    def _pg_session_guards(dbapi_connection, _record):
        # Una sesión filtrada no puede agotar el pool permanentemente.
        cursor = dbapi_connection.cursor()
        cursor.execute("SET idle_in_transaction_session_timeout = '60s'")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
