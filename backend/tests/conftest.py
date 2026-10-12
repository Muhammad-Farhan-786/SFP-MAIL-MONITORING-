import os
import pytest
from cryptography.fernet import Fernet

os.environ["JWT_SECRET"] = "test-only-" + ("x" * 40)
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["COOKIE_SECURE"] = "false"
os.environ["DELIVERY_WEBHOOK_SECRET"] = "test-webhook-secret"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.models import User, Domain
from app.security import hasher
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def db():
    target = os.environ.get("TEST_DATABASE_URL")
    if target:
        from sqlalchemy.engine import make_url

        if not (make_url(target).database or "").endswith("_tests"):
            raise ValueError("Integration test database must end in _tests")
        engine = create_engine(target)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(
            User(
                email="admin@newhotmusic.com",
                password_hash=hasher.hash("Test-password-123"),
                role="admin",
            )
        )
        session.add(
            User(
                email="viewer@newhotmusic.com",
                password_hash=hasher.hash("Test-password-123"),
                role="viewer",
            )
        )
        session.add(Domain(name="newhotmusic.com", selectors=["default"]))
        session.commit()
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.main.limit", lambda *args: None)
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def signed(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@newhotmusic.com", "password": "Test-password-123"},
    )
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    return client
