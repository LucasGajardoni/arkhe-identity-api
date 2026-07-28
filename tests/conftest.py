import base64
import os
from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["FACE_BACKEND"] = "fake"
os.environ["API_KEY_PLAINTEXT_FOR_LOCAL_ONLY"] = "test-key"
os.environ["ADMIN_PASSWORD_HASH"] = pwd.hash("admin-test")
os.environ["DATA_ENCRYPTION_KEY"] = "test-encryption-key"
os.environ["LOOKUP_HMAC_KEY"] = "test-hmac-key"
os.environ["JWT_SECRET"] = "test-jwt"

from app.api.deps import db_session
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.base import Base
from app.main import app


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    limiter.reset()
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("FACE_BACKEND", "fake")
    monkeypatch.setenv("API_KEY_PLAINTEXT_FOR_LOCAL_ONLY", "test-key")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", pwd.hash("admin-test"))
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LOOKUP_HMAC_KEY", "test-hmac-key")
    monkeypatch.setenv("JWT_SECRET", "test-jwt")
    yield
    limiter.reset()
    get_settings.cache_clear()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_db():
        yield db

    app.dependency_overrides[db_session] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def synthetic_face(color=(120, 160, 210)) -> str:
    image = Image.new("RGB", (160, 160), color)
    draw = ImageDraw.Draw(image)
    draw.ellipse((42, 32, 118, 118), fill=(230, 210, 190), outline=(30, 30, 30), width=2)
    draw.ellipse((64, 62, 72, 70), fill=(20, 20, 20))
    draw.ellipse((90, 62, 98, 70), fill=(20, 20, 20))
    draw.arc((68, 72, 94, 102), 10, 170, fill=(120, 50, 50), width=2)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
