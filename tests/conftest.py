"""Fixtures de tests ARCA — modo dual (patrón Atlas/dasic).

- Con TEST_DATABASE_URL: PostgreSQL real + `alembic upgrade head` (modo CI).
- Sin ella: SQLite en memoria + create_all (modo local rápido).

Los tests marcados @pytest.mark.postgres se omiten en modo SQLite.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  # registra todas las tablas en Base.metadata
from app.database import Base, get_db
from app.main import app as fastapi_app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if TEST_DATABASE_URL:
    test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
else:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)


def pytest_report_header(config):
    mode = "PostgreSQL (migraciones reales)" if TEST_DATABASE_URL else "SQLite en memoria (create_all)"
    return f"ARCA tests — modo BD: {mode}"


def pytest_collection_modifyitems(config, items):
    if TEST_DATABASE_URL:
        return
    skip_pg = pytest.mark.skip(reason="requiere PostgreSQL real (TEST_DATABASE_URL)")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip_pg)


if TEST_DATABASE_URL:

    @pytest.fixture(scope="session", autouse=True)
    def _apply_migrations():
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
        command.upgrade(cfg, "head")
        yield


@pytest.fixture()
def db():
    """Sesión transaccional: todo lo que haga un test se revierte al terminar."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    def _override_get_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
