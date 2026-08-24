import pytest

from app.config import _build_settings


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "arca"


def test_health_deep(client):
    response = client.get("/api/health/deep")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_config_fails_fast_in_production_without_secret(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _build_settings()


def test_config_rejects_short_secret_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("SECRET_KEY", "corta")
    with pytest.raises(RuntimeError, match="32"):
        _build_settings()


def test_config_normalizes_railway_postgres_url(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    settings = _build_settings()
    assert settings.database_url.startswith("postgresql://")
