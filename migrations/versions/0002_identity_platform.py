"""identity platform schema

Revision ID: 0002_identity_platform
Revises: 0001_initial
Create Date: 2026-08-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_identity_platform"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("allowed_origins", sa.Text(), nullable=True),
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
        sa.Column("theme", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_client_applications_slug", "client_applications", ["slug"], unique=True)

    op.create_table(
        "identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_user_id", sa.String(length=160), nullable=True),
        sa.Column("cpf_hash", sa.String(length=128), nullable=False),
        sa.Column("cpf_encrypted", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=True),
        sa.Column("email_encrypted", sa.Text(), nullable=True),
        sa.Column("phone_encrypted", sa.Text(), nullable=True),
        sa.Column("consent_version", sa.String(length=80), nullable=False),
        sa.Column("consent_purpose", sa.String(length=255), nullable=False),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_application_id"], ["client_applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_application_id", "cpf_hash", name="uq_identity_client_cpf"),
    )
    op.create_index("ix_identities_client_application_id", "identities", ["client_application_id"])
    op.create_index("ix_identities_cpf_hash", "identities", ["cpf_hash"])
    op.create_index("ix_identities_external_user_id", "identities", ["external_user_id"])

    op.create_table(
        "biometric_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_encrypted", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=False),
        sa.Column("coverage_json", sa.Text(), nullable=False),
        sa.Column("liveness_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_biometric_templates_identity_id", "biometric_templates", ["identity_id"])

    op.create_table(
        "enrollment_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_token_hash", sa.String(length=128), nullable=False),
        sa.Column("cpf_hash", sa.String(length=128), nullable=False),
        sa.Column("cpf_encrypted", sa.Text(), nullable=False),
        sa.Column("external_user_id", sa.String(length=160), nullable=True),
        sa.Column("display_name", sa.String(length=180), nullable=True),
        sa.Column("email_encrypted", sa.Text(), nullable=True),
        sa.Column("phone_encrypted", sa.Text(), nullable=True),
        sa.Column("consent_version", sa.String(length=80), nullable=False),
        sa.Column("consent_purpose", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=False),
        sa.Column("coverage_json", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("liveness_score", sa.Float(), nullable=True),
        sa.Column("next_hint", sa.String(length=120), nullable=False),
        sa.Column("captures_count", sa.Integer(), nullable=False),
        sa.Column("best_embedding_encrypted", sa.Text(), nullable=True),
        sa.Column("capture_hashes_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_application_id"], ["client_applications.id"]),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrollment_sessions_cpf_hash", "enrollment_sessions", ["cpf_hash"])
    op.create_index("ix_enrollment_sessions_session_token_hash", "enrollment_sessions", ["session_token_hash"], unique=True)

    op.create_table(
        "verification_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_token_hash", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("best_similarity", sa.Float(), nullable=True),
        sa.Column("matched", sa.Boolean(), nullable=True),
        sa.Column("capture_hashes_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_application_id"], ["client_applications.id"]),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_sessions_session_token_hash", "verification_sessions", ["session_token_hash"], unique=True)

    op.create_table(
        "verification_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verification_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("liveness_score", sa.Float(), nullable=True),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["verification_session_id"], ["verification_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_attempts_verification_session_id", "verification_attempts", ["verification_session_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_application_id"], ["client_applications.id"]),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("ix_verification_attempts_verification_session_id", table_name="verification_attempts")
    op.drop_table("verification_attempts")
    op.drop_index("ix_verification_sessions_session_token_hash", table_name="verification_sessions")
    op.drop_table("verification_sessions")
    op.drop_index("ix_enrollment_sessions_session_token_hash", table_name="enrollment_sessions")
    op.drop_index("ix_enrollment_sessions_cpf_hash", table_name="enrollment_sessions")
    op.drop_table("enrollment_sessions")
    op.drop_index("ix_biometric_templates_identity_id", table_name="biometric_templates")
    op.drop_table("biometric_templates")
    op.drop_index("ix_identities_external_user_id", table_name="identities")
    op.drop_index("ix_identities_cpf_hash", table_name="identities")
    op.drop_index("ix_identities_client_application_id", table_name="identities")
    op.drop_table("identities")
    op.drop_index("ix_client_applications_slug", table_name="client_applications")
    op.drop_table("client_applications")
