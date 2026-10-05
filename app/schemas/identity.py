from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.cpf import only_digits, validate_cpf


class ConsentInput(BaseModel):
    accepted: bool
    version: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=255)


class ClientApplicationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    client_secret: str = Field(min_length=24, max_length=255)
    allowed_origins: list[str] = Field(default_factory=list)


class ClientApplicationCreated(BaseModel):
    id: UUID
    name: str
    slug: str
    warning: str = "Client secret recebido e armazenado apenas como hash."


class EnrollmentStartRequest(BaseModel):
    cpf: str
    external_user_id: str | None = Field(default=None, max_length=160)
    display_name: str | None = Field(default=None, max_length=180)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    consent: ConsentInput
    ttl_minutes: int = Field(default=15, ge=3, le=60)

    @field_validator("cpf")
    @classmethod
    def valid_cpf(cls, value: str) -> str:
        cpf = only_digits(value)
        result = validate_cpf(cpf)
        if not result.formato_valido or not result.digitos_verificadores_validos:
            raise ValueError("CPF invalido")
        return cpf

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value: ConsentInput) -> ConsentInput:
        if not value.accepted:
            raise ValueError("Consentimento explicito obrigatorio para cadastrar biometria")
        return value


class SessionCreated(BaseModel):
    session_id: UUID
    session_token: str
    expires_at: datetime
    scanner_url: str


class CaptureInput(BaseModel):
    image_base64: str


class CaptureResult(BaseModel):
    session_id: UUID
    status: str
    coverage: dict[str, float]
    quality_score: float
    coverage_score: float
    liveness_score: float | None
    next_hint: str
    ready: bool


class EnrollmentCompleted(BaseModel):
    identity_id: UUID
    biometric_template_id: UUID
    cpf_masked: str
    status: str


class EnrollmentStatus(BaseModel):
    session_id: UUID
    identity_id: UUID | None
    status: str


class VerificationStartRequest(BaseModel):
    identity_id: UUID | None = None
    cpf: str | None = None
    purpose: str = Field(default="face_verification", min_length=1, max_length=160)
    ttl_minutes: int = Field(default=10, ge=3, le=30)

    @field_validator("cpf")
    @classmethod
    def valid_optional_cpf(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cpf = only_digits(value)
        result = validate_cpf(cpf)
        if not result.formato_valido or not result.digitos_verificadores_validos:
            raise ValueError("CPF invalido")
        return cpf


class VerificationAttemptResult(BaseModel):
    verification_session_id: UUID
    attempt_id: UUID
    identity_id: UUID | None
    matched: bool
    similarity: float | None
    threshold: float
    quality_score: float
    liveness_score: float | None
    status: str


class VerificationStatus(BaseModel):
    verification_session_id: UUID
    identity_id: UUID | None
    matched: bool | None
    status: str


class IdentityPublic(BaseModel):
    id: UUID
    client_application_id: UUID
    external_user_id: str | None
    cpf_masked: str
    display_name: str | None
    status: str
    has_biometric_template: bool
    created_at: datetime


class LoginInput(BaseModel):
    username: str
    password: str


class TokenOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
