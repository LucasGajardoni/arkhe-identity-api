from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import decrypt_text, encrypt_text, lookup_hmac, mask_cpf
from app.db.models import BiometricTemplate, ClientApplication, Identity
from app.services.cpf import only_digits


class IdentityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def client_by_slug(self, slug: str) -> ClientApplication | None:
        return self.db.scalar(select(ClientApplication).where(ClientApplication.slug == slug, ClientApplication.is_active.is_(True)))

    def client_by_id(self, client_id: UUID) -> ClientApplication | None:
        return self.db.get(ClientApplication, client_id)

    def create_client(self, *, name: str, slug: str, secret_hash: str, allowed_origins: str | None = None) -> ClientApplication:
        client = ClientApplication(name=name, slug=slug, secret_hash=secret_hash, allowed_origins=allowed_origins)
        self.db.add(client)
        self.db.flush()
        return client

    def find_identity_by_cpf(self, client_id: UUID, cpf: str) -> Identity | None:
        stmt = (
            select(Identity)
            .options(selectinload(Identity.templates))
            .where(Identity.client_application_id == client_id, Identity.cpf_hash == lookup_hmac(only_digits(cpf)))
        )
        return self.db.scalar(stmt)

    def get_identity(self, identity_id: UUID) -> Identity | None:
        return self.db.scalar(select(Identity).options(selectinload(Identity.templates)).where(Identity.id == identity_id))

    def upsert_identity(
        self,
        *,
        client_id: UUID,
        cpf: str,
        external_user_id: str | None,
        display_name: str | None,
        email: str | None,
        phone: str | None,
        consent_version: str,
        consent_purpose: str,
    ) -> Identity:
        identity = self.find_identity_by_cpf(client_id, cpf)
        if identity is None:
            identity = Identity(
                client_application_id=client_id,
                cpf_hash=lookup_hmac(only_digits(cpf)),
                cpf_encrypted=encrypt_text(only_digits(cpf)) or "",
                external_user_id=external_user_id,
                display_name=display_name,
                email_encrypted=encrypt_text(email),
                phone_encrypted=encrypt_text(phone),
                consent_version=consent_version,
                consent_purpose=consent_purpose,
                consent_accepted_at=datetime.now(UTC),
            )
            self.db.add(identity)
            self.db.flush()
            return identity

        identity.external_user_id = external_user_id or identity.external_user_id
        identity.display_name = display_name or identity.display_name
        identity.email_encrypted = encrypt_text(email) if email is not None else identity.email_encrypted
        identity.phone_encrypted = encrypt_text(phone) if phone is not None else identity.phone_encrypted
        identity.consent_version = consent_version
        identity.consent_purpose = consent_purpose
        identity.consent_accepted_at = datetime.now(UTC)
        return identity

    def add_template(
        self,
        *,
        identity: Identity,
        embedding_encrypted: str,
        model_name: str,
        model_version: str,
        quality_score: float,
        coverage_score: float,
        coverage_json: str,
        liveness_score: float | None,
    ) -> BiometricTemplate:
        for template in identity.templates:
            if template.status == "active":
                template.status = "revoked"
                template.revoked_at = datetime.now(UTC)
        template = BiometricTemplate(
            identity_id=identity.id,
            embedding_encrypted=embedding_encrypted,
            model_name=model_name,
            model_version=model_version,
            quality_score=quality_score,
            coverage_score=coverage_score,
            coverage_json=coverage_json,
            liveness_score=liveness_score,
        )
        self.db.add(template)
        self.db.flush()
        return template

    @staticmethod
    def public_identity(identity: Identity) -> dict[str, object]:
        cpf = decrypt_text(identity.cpf_encrypted)
        active_templates = [template for template in identity.templates if template.status == "active"]
        return {
            "id": identity.id,
            "client_application_id": identity.client_application_id,
            "external_user_id": identity.external_user_id,
            "cpf_masked": mask_cpf(cpf) or "***",
            "display_name": identity.display_name,
            "status": identity.status,
            "has_biometric_template": bool(active_templates),
            "created_at": identity.created_at,
        }
