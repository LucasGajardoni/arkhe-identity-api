from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import EnrollmentSession
from app.services.coverage import coverage_ready, update_coverage
from app.services.facial import FaceEmbeddingResult
from app.services.liveness import PassiveLivenessService
from tests.helpers import (
    create_client_app,
    image_base64,
    patch_pose_sequence,
    start_enrollment,
)


def test_next_hint_requests_left_when_left_is_weak():
    current = {"frontal": 1.0, "left": 0.1, "right": 0.9, "up": 0.8, "down": 0.8}
    result = update_coverage(current, {"left": 0.2}, 1.0)
    assert result.next_hint == "turn_left"


def test_next_hint_requests_right_when_right_is_weak():
    current = {"frontal": 1.0, "left": 0.9, "right": 0.1, "up": 0.8, "down": 0.8}
    result = update_coverage(current, {"right": 0.2}, 1.0)
    assert result.next_hint == "turn_right"


def test_ready_true_depends_on_coverage_not_order():
    coverage = {"frontal": 0.92, "left": 0.81, "right": 0.78, "up": 0.75, "down": 0.74}
    assert coverage_ready(coverage, 0.88) is True


def test_coverage_updates_and_next_hint_changes_dynamically(client: TestClient, db: Session, monkeypatch):
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
    first = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers=headers,
        json={"image_base64": image_base64((200, 120, 80))},
    ).json()
    second = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers=headers,
        json={"image_base64": image_base64((80, 120, 200))},
    ).json()
    assert first["coverage"]["right"] < first["coverage"]["left"]
    assert first["next_hint"] == "turn_right"
    assert second["ready"] is True
    assert second["next_hint"] == "complete"


def test_enrollment_incomplete_cannot_complete(client: TestClient, db: Session):
    create_client_app(db)
    session = start_enrollment(client).json()
    res = client.post(
        f"/v1/enrollments/{session['session_id']}/complete",
        headers={"Authorization": f"Bearer {session['session_token']}"},
    )
    assert res.status_code == 409


def test_liveness_approved_and_limited():
    import numpy as np

    result = FaceEmbeddingResult(embedding=np.ones(4), quality=0.8, face_count=1)
    liveness = PassiveLivenessService().evaluate(result)
    assert liveness.passed is True
    assert liveness.limited is True
    assert liveness.provider == "passive-quality-v1"


def test_liveness_reproved(client: TestClient, db: Session, monkeypatch):
    from app.services.liveness import LivenessResult, PassiveLivenessService

    create_client_app(db)
    patch_pose_sequence(monkeypatch, [{"frontal": 1, "left": 1, "right": 1, "up": 1, "down": 1}])
    session = start_enrollment(client).json()

    def fail_liveness(_self, _face):
        return LivenessResult(score=0.1, passed=False, provider="test", limited=True)

    monkeypatch.setattr(PassiveLivenessService, "evaluate", fail_liveness)
    res = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": image_base64((120, 160, 210))},
    )
    assert res.status_code == 422
    assert "Liveness" in res.text


def test_expired_session_sets_status(client: TestClient, db: Session):
    create_client_app(db)
    session = start_enrollment(client).json()
    record = db.get(EnrollmentSession, UUID(session["session_id"]))
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    res = client.post(
        f"/v1/enrollments/{session['session_id']}/captures",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"image_base64": image_base64((120, 160, 210))},
    )
    assert res.status_code == 410
    assert record.status == "expired"
