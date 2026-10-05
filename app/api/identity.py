from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import db_session, rate_limit, require_client_application
from app.db.models import ClientApplication, EnrollmentSession, VerificationSession
from app.repositories.identity_repository import IdentityRepository
from app.schemas.identity import (
    CaptureInput,
    CaptureResult,
    EnrollmentCompleted,
    EnrollmentStartRequest,
    EnrollmentStatusResult,
    IdentityPublic,
    SessionCreated,
    VerificationAttemptResult,
    VerificationStartRequest,
    VerificationStatusResult,
)
from app.services.coverage import load_coverage
from app.services.sessions import IdentitySessionService, cpf_mask_from_identity

router = APIRouter(prefix="/v1", tags=["face-identity"])


def bearer_token(authorization: str = Header(default="")) -> str:
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return authorization.strip()


@router.post("/enrollments", response_model=SessionCreated, status_code=201)
def start_enrollment(
    payload: EnrollmentStartRequest,
    request: Request,
    _: None = Depends(rate_limit),
    db: Session = Depends(db_session),
    client: ClientApplication = Depends(require_client_application),
):
    session, token = IdentitySessionService(db).start_enrollment(client, payload, str(request.base_url))
    db.commit()
    return SessionCreated(
        session_id=session.id,
        session_token=token,
        expires_at=session.expires_at,
        scanner_url=str(request.url_for("scanner_page")) + f"?mode=enroll&session_id={session.id}#token={token}",
    )


@router.post("/enrollments/{session_id}/captures", response_model=CaptureResult)
def capture_enrollment(
    session_id: UUID,
    payload: CaptureInput,
    _: None = Depends(rate_limit),
    token: str = Depends(bearer_token),
    db: Session = Depends(db_session),
):
    session = IdentitySessionService(db).capture_enrollment(session_id, token, payload.image_base64)
    db.commit()
    return CaptureResult(
        session_id=session.id,
        status=session.status,
        coverage=load_coverage(session.coverage_json),
        quality_score=session.quality_score,
        coverage_score=session.coverage_score,
        liveness_score=session.liveness_score,
        next_hint=session.next_hint,
        ready=IdentitySessionService.enrollment_ready(session),
    )


@router.post("/enrollments/{session_id}/complete", response_model=EnrollmentCompleted)
def complete_enrollment(session_id: UUID, token: str = Depends(bearer_token), db: Session = Depends(db_session)):
    identity, template = IdentitySessionService(db).complete_enrollment(session_id, token)
    db.commit()
    return EnrollmentCompleted(
        identity_id=identity.id,
        biometric_template_id=template.id,
        cpf_masked=cpf_mask_from_identity(identity),
        status="completed",
    )


@router.get("/enrollments/{session_id}", response_model=EnrollmentStatusResult)
def enrollment_status(
    session_id: UUID,
    db: Session = Depends(db_session),
    client: ClientApplication = Depends(require_client_application),
):
    session = db.get(EnrollmentSession, session_id)

    if session is None or session.client_application_id != client.id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessao nao encontrada.")

    return EnrollmentStatusResult(
        enrollment_session_id=session.id,
        identity_id=session.identity_id,
        status=session.status,
        expires_at=session.expires_at,
    )


@router.post("/verifications", response_model=SessionCreated, status_code=201)
def start_verification(
    payload: VerificationStartRequest,
    request: Request,
    _: None = Depends(rate_limit),
    db: Session = Depends(db_session),
    client: ClientApplication = Depends(require_client_application),
):
    session, token = IdentitySessionService(db).start_verification(client, payload, str(request.base_url))
    db.commit()
    return SessionCreated(
        session_id=session.id,
        session_token=token,
        expires_at=session.expires_at,
        scanner_url=str(request.url_for("scanner_page")) + f"?mode=verify&session_id={session.id}#token={token}",
    )


@router.post("/verifications/{session_id}/attempts", response_model=VerificationAttemptResult)
def attempt_verification(
    session_id: UUID,
    payload: CaptureInput,
    _: None = Depends(rate_limit),
    token: str = Depends(bearer_token),
    db: Session = Depends(db_session),
):
    service = IdentitySessionService(db)
    attempt = service.attempt_verification(session_id, token, payload.image_base64)
    session = service.get_verification(session_id, token)
    db.commit()
    return VerificationAttemptResult(
        verification_session_id=session.id,
        attempt_id=attempt.id,
        identity_id=session.identity_id,
        matched=attempt.matched,
        similarity=attempt.similarity,
        threshold=service.settings.facial_similarity_threshold,
        quality_score=attempt.quality_score,
        liveness_score=attempt.liveness_score,
        status=session.status,
    )


@router.get("/verifications/{session_id}", response_model=VerificationStatusResult)
def verification_status(
    session_id: UUID,
    db: Session = Depends(db_session),
    client: ClientApplication = Depends(require_client_application),
):
    session = db.get(VerificationSession, session_id)

    if session is None or session.client_application_id != client.id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessao nao encontrada.")

    return VerificationStatusResult(
        verification_session_id=session.id,
        identity_id=session.identity_id,
        matched=session.matched,
        status=session.status,
        expires_at=session.expires_at,
    )


@router.get("/identities/{identity_id}", response_model=IdentityPublic)
def get_identity(
    identity_id: UUID,
    db: Session = Depends(db_session),
    client: ClientApplication = Depends(require_client_application),
):
    identity = IdentityRepository(db).get_identity(identity_id)
    if identity is None or identity.client_application_id != client.id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identidade nao encontrada.")
    return IdentityRepository.public_identity(identity)
