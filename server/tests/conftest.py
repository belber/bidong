import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _clear_parse_cache():
    from app.services.parse_cache import parse_cache

    parse_cache.clear()
    yield
    parse_cache.clear()


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    testing_session = sessionmaker(
        bind=db_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    settings.dev_mode = True
    settings.storage_backend = "local"
    settings.local_storage_dir = tempfile.mkdtemp()
    settings.public_base_url = "http://testserver"
    settings.jwt_secret = "test-secret-0123456789abcdefghijklmnopqrstuvwxyz"

    c = TestClient(app)
    yield c
    c.close()
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    resp = client.post("/api/login", json={"code": "dev_user1"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_client(db_engine, monkeypatch):
    """管理端（独立 app）的测试客户端，密码用默认开发密码。"""
    from app.admin_app import app as admin_app
    from app.db import get_db

    testing_session = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )
    settings.admin_password = "admin-dev-password"
    settings.dev_mode = False  # 避免 lifespan 去真实 DB 建表/播种
    monkeypatch.setattr("app.services.config_store.seed_defaults", lambda db: None)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    admin_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(admin_app)
    yield client
    client.close()
    admin_app.dependency_overrides.clear()
