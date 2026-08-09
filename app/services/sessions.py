import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_text, encrypt_text, lookup_hmac, mask_cpf, pwd_context
from app.db.models import (
    AuditEvent,
    BiometricTemplate,
    ClientApplication,
    EnrollmentSession,
    Identity,
    VerificationAttempt,
    VerificationSession,
)
from app.repositories.identity_repository import IdentityRepository
from app.schemas.identity import EnrollmentStartRequest, VerificationStartRequest
from app.services.coverage import (
    coverage_ready,
    dump_coverage,
    empty_coverage,
    estimate_pose_scores,
    load_coverage,
    update_coverage,
)
from app.services.facial import FacialService
from app.services.files import decode_base64_image
from app.services.liveness import PassiveLivenessService


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return lookup_hmac(f"session:{token}")


def hash_client_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def utc_value(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def image_replay_hash(image_base64: str) -> str:
    return lookup_hmac(f"capture:{hashlib.sha256(image_base64.encode('utf-8')).hexdigest()}")


def load_hashes(raw: str | None) -> set[str]:
    if not raw:
        return set()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    return {str(item) for item in loaded}


def dump_hashes(values: set[str]) -> str:
    return json.dumps(sorted(values))


class IdentitySessionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = IdentityRepository(db)
        self.faces = FacialService()
        self.liveness = PassiveLivenessService()
        self.settings = get_settings()

    def start_enrollment(self, client: ClientApplication, request: EnrollmentStartRequest, base_url: str) -> tuple[EnrollmentSession, str]:
        token = new_session_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=request.ttl_minutes)
        session = EnrollmentSession(
            client_application_id=client.id,
            session_token_hash=hash_token(token),
            cpf_hash=lookup_hmac(request.cpf),
            cpf_encrypted=encrypt_text(request.cpf) or "",
            external_user_id=request.external_user_id,
            display_name=request.display_name,
            email_encrypted=encrypt_text(str(request.email)) if request.email else None,
            phone_encrypted=encrypt_text(request.phone),
            consent_version=request.consent.version,
            consent_purpose=request.consent.purpose,
            coverage_json=dump_coverage(empty_coverage()),
            capture_hashes_json="[]",
            expires_at=expires_at,
        )
        self.db.add(session)
        self.audit(client.id, None, "enrollment.created", "ok")
        self.db.flush()
        return session, token

    def capture_enrollment(self, session_id: UUID, token: str, image_base64: str) -> EnrollmentSession:
        session = self.get_enrollment(session_id, token)
        if session.status == "completed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sessao de cadastro ja concluida.")
        replay_hash = image_replay_hash(image_base64)
        capture_hashes = load_hashes(session.capture_hashes_json)
        if replay_hash in capture_hashes:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Frame repetido rejeitado.")
        image = decode_base64_image(image_base64)
        result = self.faces.generate_embedding(image)
        liveness = self.liveness.evaluate(result)
        if not liveness.passed:
            session.liveness_score = liveness.score
            self.audit(session.client_application_id, None, "enrollment.capture", "liveness_failed")
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Liveness insuficiente.")
        coverage = update_coverage(load_coverage(session.coverage_json), estimate_pose_scores(image), result.quality)
        capture_hashes.add(replay_hash)
        session.captures_count += 1
        session.quality_score = max(session.quality_score, result.quality)
        session.coverage_json = dump_coverage(coverage.coverage)
        session.coverage_score = coverage.score
        session.liveness_score = liveness.score
        session.next_hint = coverage.next_hint
        session.capture_hashes_json = dump_hashes(capture_hashes)
        session.best_embedding_encrypted = self.faces.encrypt_embedding(result.embedding)
        session.status = "ready" if self.enrollment_ready(session) else "capturing"
        self.audit(session.client_application_id, None, "enrollment.capture", "ok")
        return session

    def complete_enrollment(self, session_id: UUID, token: str) -> tuple[Identity, BiometricTemplate]:
        session = self.get_enrollment(session_id, token)
        if not self.enrollment_ready(session) or not session.best_embedding_encrypted:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sessao ainda nao possui biometria suficiente.")
        cpf = decrypt_text(session.cpf_encrypted) or ""
        identity = self.repo.upsert_identity(
            client_id=session.client_application_id,
            cpf=cpf,
            external_user_id=session.external_user_id,
            display_name=session.display_name,
            email=decrypt_text(session.email_encrypted),
            phone=decrypt_text(session.phone_encrypted),
            consent_version=session.consent_version,
            consent_purpose=session.consent_purpose,
        )
        template = self.repo.add_template(
            identity=identity,
            embedding_encrypted=session.best_embedding_encrypted,
            model_name=self.settings.face_backend,
            model_version="local-v1",
            quality_score=session.quality_score,
            coverage_score=session.coverage_score,
            coverage_json=session.coverage_json,
            liveness_score=session.liveness_score,
        )
        session.identity_id = identity.id
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
        self.audit(session.client_application_id, identity.id, "enrollment.completed", "ok")
        return identity, template

    def start_verification(
        self, client: ClientApplication, request: VerificationStartRequest, base_url: str
    ) -> tuple[VerificationSession, str]:
        identity = None
        if request.identity_id:
            identity = self.repo.get_identity(request.identity_id)
            if identity and identity.client_application_id != client.id:
                identity = None
        elif request.cpf:
            identity = self.repo.find_identity_by_cpf(client.id, request.cpf)
        if identity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identidade nao encontrada.")
        token = new_session_token()
        session = VerificationSession(
            client_application_id=client.id,
            identity_id=identity.id,
            session_token_hash=hash_token(token),
            purpose=request.purpose,
            capture_hashes_json="[]",
            expires_at=datetime.now(UTC) + timedelta(minutes=request.ttl_minutes),
        )
        self.db.add(session)
        self.audit(client.id, identity.id, "verification.created", "ok")
        self.db.flush()
        return session, token

    def attempt_verification(self, session_id: UUID, token: str, image_base64: str) -> VerificationAttempt:
        session = self.get_verification(session_id, token)
        if session.status in {"matched", "not_matched"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sessao de verificacao ja consumida.")
        replay_hash = image_replay_hash(image_base64)
        capture_hashes = load_hashes(session.capture_hashes_json)
        if replay_hash in capture_hashes:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Frame repetido rejeitado.")
        identity = self.repo.get_identity(session.identity_id) if session.identity_id else None
        template = self.active_template(identity) if identity else None
        if template is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identidade sem template facial ativo.")
        probe = self.faces.generate_embedding(decode_base64_image(image_base64))
        liveness = self.liveness.evaluate(probe)
        if not liveness.passed:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Liveness insuficiente.")
        stored = self.faces.decrypt_embedding(template.embedding_encrypted)
        similarity = self.faces.similarity(probe.embedding, stored)
        matched = similarity >= self.settings.facial_similarity_threshold
        attempt = VerificationAttempt(
            verification_session_id=session.id,
            similarity=similarity,
            quality_score=probe.quality,
            liveness_score=liveness.score,
            matched=matched,
            failure_code=None if matched else "FACE_MISMATCH",
        )
        self.db.add(attempt)
        session.best_similarity = max(session.best_similarity or 0.0, similarity)
        session.matched = matched
        session.status = "matched" if matched else "not_matched"
        capture_hashes.add(replay_hash)
        session.capture_hashes_json = dump_hashes(capture_hashes)
        session.completed_at = datetime.now(UTC)
        self.audit(session.client_application_id, session.identity_id, "verification.attempt", "matched" if matched else "not_matched")
        self.db.flush()
        return attempt

    def get_enrollment(self, session_id: UUID, token: str) -> EnrollmentSession:
        session = self.db.get(EnrollmentSession, session_id)
        if session is None or session.session_token_hash != hash_token(token):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessao nao encontrada.")
        if utc_value(session.expires_at) < datetime.now(UTC):
            session.status = "expired"
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Sessao expirada.")
        return session

    def get_verification(self, session_id: UUID, token: str) -> VerificationSession:
        session = self.db.get(VerificationSession, session_id)
        if session is None or session.session_token_hash != hash_token(token):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessao nao encontrada.")
        if utc_value(session.expires_at) < datetime.now(UTC):
            session.status = "expired"
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Sessao expirada.")
        return session

    @staticmethod
    def enrollment_ready(session: EnrollmentSession) -> bool:
        return coverage_ready(load_coverage(session.coverage_json), session.quality_score) and session.best_embedding_encrypted is not None

    @staticmethod
    def active_template(identity: Identity | None) -> BiometricTemplate | None:
        if identity is None:
            return None
        active = [template for template in identity.templates if template.status == "active"]
        return sorted(active, key=lambda template: template.created_at, reverse=True)[0] if active else None

    def audit(self, client_id, identity_id, event_type: str, outcome: str) -> None:
        self.db.add(AuditEvent(client_application_id=client_id, identity_id=identity_id, event_type=event_type, outcome=outcome))


def cpf_mask_from_identity(identity: Identity) -> str:
    return mask_cpf(decrypt_text(identity.cpf_encrypted)) or "***"
