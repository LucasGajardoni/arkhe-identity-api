import base64
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EnrollmentSession, Identity
from app.repositories.identity_repository import IdentityRepository
from app.services.sessions import hash_client_secret
from tests.conftest import synthetic_face

CLIENT_SECRET = "secret-test"


def create_client_app(db: Session, slug: str = "test-client"):
    existing = IdentityRepository(db).client_by_slug(slug)
    if existing is not None:
        return existing
    client = IdentityRepository(db).create_client(
        name="Test Client",
        slug=slug,
        secret_hash=hash_client_secret(CLIENT_SECRET),
    )
    db.commit()
    return client


def auth_headers(secret: str = CLIENT_SECRET, slug: str = "test-client") -> dict[str, str]:  # noqa: S107
    return {"X-Client-Id": slug, "X-Client-Secret": secret}


def enrollment_payload(cpf: str = "529.982.247-25") -> dict[str, object]:
    return {
        "cpf": cpf,
        "external_user_id": "user-1",
        "display_name": "Pessoa Teste",
        "consent": {"accepted": True, "version": "terms-v1", "purpose": "Autenticacao facial"},
    }


def start_enrollment(client: TestClient, cpf: str = "529.982.247-25"):
    return client.post("/v1/enrollments", headers=auth_headers(), json=enrollment_payload(cpf))


def image_base64(color: tuple[int, int, int]) -> str:
    return synthetic_face(color)


def tiny_image_base64() -> str:
    image = Image.new("RGB", (6, 6), (120, 120, 120))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def solid_image_base64() -> str:
    image = Image.new("RGB", (160, 160), (10, 10, 10))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def patch_pose_sequence(monkeypatch, poses: Iterable[dict[str, float]]) -> None:
    remaining = list(poses)

    def fake_pose(_image):
        if remaining:
            return remaining.pop(0)
        return {"frontal": 1.0, "left": 1.0, "right": 1.0, "up": 1.0, "down": 1.0}

    monkeypatch.setattr("app.services.sessions.estimate_pose_scores", fake_pose)


def complete_identity(client: TestClient, db: Session, monkeypatch) -> tuple[str, str]:
    create_client_app(db)
    patch_pose_sequence(
        monkeypatch,
        [
            {"frontal": 1.0, "left": 0.9, "right": 0.2, "up": 0.8, "down": 0.8},
            {"frontal": 1.0, "left": 0.9, "right": 1.0, "up": 0.8, "down": 0.8},
        ],
    )
    session = start_enrollment(client).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers=headers,
        json={"image_base64": image_base64((190, 120, 80))},
    )
    client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers=headers,
        json={"image_base64": image_base64((80, 120, 190))},
    )
    identity_id = client.post(f"/v1/enrollments/{session['session_id']}/complete", headers=headers).json()["identity_id"]
    return identity_id, image_base64((80, 120, 190))


def expire_enrollment(db: Session, session_id: str) -> None:
    session = db.get(EnrollmentSession, UUID(session_id))
    assert session is not None
    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()


def identity_count(db: Session) -> int:
    return len(db.scalars(select(Identity)).all())
