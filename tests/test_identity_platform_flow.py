from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import (
    auth_headers,
    complete_identity,
    create_client_app,
    enrollment_payload,
    identity_count,
    image_base64,
    patch_pose_sequence,
    start_enrollment,
)


def test_create_client_application_admin(client: TestClient):
    token = client.post("/admin/auth/login", json={"username": "admin", "password": "admin-test"}).json()["access_token"]
    res = client.post(
        "/admin/client-applications",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Portal", "slug": "portal", "client_secret": "portal-secret-with-enough-size", "allowed_origins": []},
    )
    assert res.status_code == 201
    assert "client_secret" not in res.text


def test_client_auth_success_creates_enrollment(client: TestClient, db: Session):
    create_client_app(db)
    res = start_enrollment(client)
    assert res.status_code == 201
    assert res.json()["session_token"]


def test_identity_creation_normalizes_cpf_and_masks_response(client: TestClient, db: Session, monkeypatch):
    create_client_app(db)
    patch_pose_sequence(
        monkeypatch,
        [
            {"frontal": 1.0, "left": 0.9, "right": 0.2, "up": 0.8, "down": 0.8},
            {"frontal": 1.0, "left": 0.9, "right": 1.0, "up": 0.8, "down": 0.8},
        ],
    )
    session = client.post("/v1/enrollments", headers=auth_headers(), json=enrollment_payload("529.982.247-25")).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    client.post(f"/v1/enrollments/{session['session_id']}/captures", headers=headers, json={"image_base64": image_base64((200, 120, 80))})
    client.post(f"/v1/enrollments/{session['session_id']}/captures", headers=headers, json={"image_base64": image_base64((80, 120, 200))})
    complete = client.post(f"/v1/enrollments/{session['session_id']}/complete", headers=headers)
    assert complete.status_code == 200
    assert complete.json()["cpf_masked"] == "529.***.***-25"
    assert "52998224725" not in complete.text


def test_duplicate_cpf_reuses_identity_for_same_client(client: TestClient, db: Session, monkeypatch):
    first_id, _ = complete_identity(client, db, monkeypatch)
    second_id, _ = complete_identity(client, db, monkeypatch)
    assert second_id == first_id
    assert identity_count(db) == 1


def test_create_verification_session(client: TestClient, db: Session, monkeypatch):
    identity_id, _ = complete_identity(client, db, monkeypatch)
    res = client.post("/v1/verifications", headers=auth_headers(), json={"identity_id": identity_id, "purpose": "login"})
    assert res.status_code == 201
    assert res.json()["session_token"]


def test_verification_matched(client: TestClient, db: Session, monkeypatch):
    identity_id, reference = complete_identity(client, db, monkeypatch)
    session = client.post("/v1/verifications", headers=auth_headers(), json={"identity_id": identity_id}).json()
    attempt = client.post(
        f"/v1/verifications/{session['session_id']}/attempts",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": reference},
    )
    assert attempt.status_code == 200
    assert attempt.json()["matched"] is True


def test_verification_not_matched_and_threshold(client: TestClient, db: Session, monkeypatch):
    identity_id, _ = complete_identity(client, db, monkeypatch)
    monkeypatch.setattr("app.services.facial.FacialService.similarity", staticmethod(lambda _left, _right: 0.1))
    session = client.post("/v1/verifications", headers=auth_headers(), json={"identity_id": identity_id}).json()
    attempt = client.post(
        f"/v1/verifications/{session['session_id']}/attempts",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": image_base64((20, 40, 80))},
    )
    assert attempt.status_code == 200
    assert attempt.json()["matched"] is False
    assert attempt.json()["threshold"] == 0.85


def test_verification_mismatch_keeps_session_open_for_retry(client: TestClient, db: Session, monkeypatch):
    identity_id, _ = complete_identity(client, db, monkeypatch)
    monkeypatch.setattr("app.services.facial.FacialService.similarity", staticmethod(lambda _left, _right: 0.1))
    session = client.post("/v1/verifications", headers=auth_headers(), json={"identity_id": identity_id}).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    first = client.post(
        f"/v1/verifications/{session['session_id']}/attempts",
        headers=headers,
        json={"image_base64": image_base64((20, 40, 80))},
    )
    second = client.post(
        f"/v1/verifications/{session['session_id']}/attempts",
        headers=headers,
        json={"image_base64": image_base64((40, 80, 120))},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "capturing"
    assert second.status_code == 200
    assert second.json()["matched"] is False


def test_verification_closes_after_three_mismatches(client: TestClient, db: Session, monkeypatch):
    identity_id, _ = complete_identity(client, db, monkeypatch)
    monkeypatch.setattr("app.services.facial.FacialService.similarity", staticmethod(lambda _left, _right: 0.1))

    session = client.post("/v1/verifications", headers=auth_headers(), json={"identity_id": identity_id}).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}

    for cor in ((20, 40, 80), (40, 80, 120), (80, 120, 160)):
        resposta = client.post(
            f"/v1/verifications/{session['session_id']}/attempts",
            headers=headers,
            json={"image_base64": image_base64(cor)},
        )

    assert resposta.status_code == 200
    assert resposta.json()["matched"] is False
    assert resposta.json()["status"] == "not_matched"

    quarta = client.post(
        f"/v1/verifications/{session['session_id']}/attempts",
        headers=headers,
        json={"image_base64": image_base64((120, 160, 200))},
    )

    assert quarta.status_code == 409
