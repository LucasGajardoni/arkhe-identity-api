import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.logging import SensitiveDataFilter
from app.db.models import EnrollmentSession
from tests.helpers import (
    auth_headers,
    complete_identity,
    create_client_app,
    expire_enrollment,
    image_base64,
    patch_pose_sequence,
    solid_image_base64,
    start_enrollment,
    tiny_image_base64,
)


@pytest.mark.parametrize(
    ("headers", "status_code"),
    [
        ({"X-Client-Id": "missing", "X-Client-Secret": "secret-test"}, 401),
        (auth_headers("wrong"), 401),
    ],
)
def test_invalid_client_credentials(client: TestClient, db: Session, headers: dict[str, str], status_code: int):
    create_client_app(db)
    res = client.post("/v1/enrollments", headers=headers, json={})
    assert res.status_code == status_code


def test_session_token_valid_invalid_and_expired(client: TestClient, db: Session):
    create_client_app(db)
    session = start_enrollment(client).json()
    valid = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": tiny_image_base64()},
    )
    invalid = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers={"Authorization": "Bearer wrong"},
        json={"image_base64": tiny_image_base64()},
    )
    expire_enrollment(db, session["session_id"])
    expired = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": tiny_image_base64()},
    )
    assert valid.status_code == 422
    assert invalid.status_code == 404
    assert expired.status_code == 410


def test_session_token_reuse_after_complete_is_rejected(client: TestClient, db: Session, monkeypatch):
    create_client_app(db)
    patch_pose_sequence(
        monkeypatch,
        [
            {"frontal": 1.0, "left": 0.9, "right": 0.2, "up": 0.8, "down": 0.8},
            {"frontal": 1.0, "left": 0.9, "right": 1.0, "up": 0.8, "down": 0.8},
        ],
    )
    started = start_enrollment(client).json()
    headers = {"Authorization": f"Bearer {started['session_token']}"}
    client.post(
        f"/v1/enrollments/{started['session_id']}/captures",
        headers=headers,
        json={"image_base64": image_base64((190, 120, 80))},
    )
    client.post(
        f"/v1/enrollments/{started['session_id']}/captures",
        headers=headers,
        json={"image_base64": image_base64((80, 120, 190))},
    )
    complete = client.post(f"/v1/enrollments/{started['session_id']}/complete", headers=headers)
    assert complete.status_code == 200
    session = db.get(EnrollmentSession, UUID(started["session_id"]))
    res = client.post(
        f"/v1/enrollments/{session.id}/captures",
        headers=headers,
        json={"image_base64": image_base64((10, 10, 10))},
    )
    assert res.status_code == 409


def test_replay_frame_rejected(client: TestClient, db: Session, monkeypatch):
    create_client_app(db)
    patch_pose_sequence(monkeypatch, [{"frontal": 1, "left": 1, "right": 0, "up": 1, "down": 1}])
    session = start_enrollment(client).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    image = image_base64((200, 120, 80))
    first = client.post(f"/v1/enrollments/{session['session_id']}/captures", headers=headers, json={"image_base64": image})
    second = client.post(f"/v1/enrollments/{session['session_id']}/captures", headers=headers, json={"image_base64": image})
    assert first.status_code == 200
    assert second.status_code == 409


def test_capture_without_face_and_low_quality(client: TestClient, db: Session):
    create_client_app(db)
    session = start_enrollment(client).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    no_face = client.post(f"/v1/enrollments/{session['session_id']}/captures", headers=headers, json={"image_base64": tiny_image_base64()})
    low_quality = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers=headers,
        json={"image_base64": solid_image_base64()},
    )
    assert no_face.status_code == 422
    assert low_quality.status_code == 422


def test_multiple_faces_error_is_returned(client: TestClient, db: Session, monkeypatch):
    from app.core.exceptions import ArkheError
    from app.services.facial import FacialService

    create_client_app(db)
    session = start_enrollment(client).json()

    def raise_multiple(_self, _image):
        raise ArkheError("ARKHE_MULTIPLE_FACES", "Mais de uma face detectada.")

    monkeypatch.setattr(FacialService, "generate_embedding", raise_multiple)
    res = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": image_base64((120, 160, 210))},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "ARKHE_MULTIPLE_FACES"


def test_rate_limiting(client: TestClient, db: Session):
    create_client_app(db)
    responses = [client.post("/v1/enrollments", headers=auth_headers(), json={}) for _ in range(11)]
    assert responses[-1].status_code == 429


def test_cors_preflight(client: TestClient):
    res = client.options(
        "/v1/enrollments",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Client-Id,X-Client-Secret,Content-Type",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:8000"


def test_admin_endpoints_are_protected(client: TestClient):
    res = client.get("/admin/client-applications")
    assert res.status_code == 401


def test_secrets_embeddings_and_biometrics_not_exposed(client: TestClient, db: Session, monkeypatch):
    identity_id, _ = complete_identity(client, db, monkeypatch)
    listed = client.get(f"/v1/identities/{identity_id}", headers=auth_headers())
    assert "secret-test" not in listed.text
    assert "embedding" not in listed.text.lower()
    assert "image_base64" not in listed.text


def test_sensitive_data_filter_redacts_logs(caplog):
    logger = logging.getLogger("identity-test")
    logger.addFilter(SensitiveDataFilter())
    caplog.set_level(logging.INFO)
    logger.info("cpf=52998224725 image=%s", "A" * 120)
    assert "52998224725" not in caplog.text
    assert "A" * 120 not in caplog.text
    assert "[CPF_REDACTED]" in caplog.text
    assert "[BASE64_REDACTED]" in caplog.text
