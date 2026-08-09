import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class ClientApplication(Base):
    __tablename__ = "client_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed_origins: Mapped[str | None] = mapped_column(Text)
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    theme: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    identities: Mapped[list["Identity"]] = relationship(back_populates="client_application", cascade="all, delete-orphan")


class Identity(Base):
    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("client_application_id", "cpf_hash", name="uq_identity_client_cpf"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(160), index=True)
    cpf_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cpf_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(180))
    email_encrypted: Mapped[str | None] = mapped_column(Text)
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    consent_purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    consent_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    client_application: Mapped[ClientApplication] = relationship(back_populates="identities")
    templates: Mapped[list["BiometricTemplate"]] = relationship(back_populates="identity", cascade="all, delete-orphan")


class BiometricTemplate(Base):
    __tablename__ = "biometric_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("identities.id", ondelete="CASCADE"), index=True)
    embedding_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_score: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    liveness_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    identity: Mapped[Identity] = relationship(back_populates="templates")


class EnrollmentSession(Base):
    __tablename__ = "enrollment_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("client_applications.id"))
    identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("identities.id", ondelete="SET NULL"))
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    cpf_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cpf_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(160))
    display_name: Mapped[str | None] = mapped_column(String(180))
    email_encrypted: Mapped[str | None] = mapped_column(Text)
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    consent_purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    coverage_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    liveness_score: Mapped[float | None] = mapped_column(Float)
    next_hint: Mapped[str] = mapped_column(String(120), default="center_face", nullable=False)
    captures_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_embedding_encrypted: Mapped[str | None] = mapped_column(Text)
    capture_hashes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationSession(Base):
    __tablename__ = "verification_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("client_applications.id"))
    identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("identities.id", ondelete="SET NULL"))
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    best_similarity: Mapped[float | None] = mapped_column(Float)
    matched: Mapped[bool | None] = mapped_column(Boolean)
    capture_hashes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verification_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verification_sessions.id", ondelete="CASCADE"), index=True
    )
    similarity: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    liveness_score: Mapped[float | None] = mapped_column(Float)
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("client_applications.id"))
    identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("identities.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent_hash: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
