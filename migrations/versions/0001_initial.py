"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cpf_hash", sa.String(length=64), nullable=False),
        sa.Column("cpf_encrypted", sa.Text(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("nome_social", sa.String(length=255), nullable=True),
        sa.Column("data_nascimento", sa.Date(), nullable=False),
        sa.Column("sexo", sa.String(length=1), nullable=False),
        sa.Column("nacionalidade", sa.String(length=40), nullable=False),
        sa.Column("nome_mae", sa.String(length=255), nullable=True),
        sa.Column("nome_pai", sa.String(length=255), nullable=True),
        sa.Column("situacao_cpf_interna", sa.String(length=40), nullable=False),
        sa.Column("data_inscricao_cpf", sa.Date(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("telefone", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("consentimento_aceito_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("versao_termo_consentimento", sa.String(length=40), nullable=True),
        sa.Column("finalidade_consentimento", sa.Text(), nullable=True),
        sa.Column("exclusao_solicitada_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_persons_cpf_hash", "persons", ["cpf_hash"], unique=True)
    op.create_index("ix_persons_nome", "persons", ["nome"])
    op.create_index("ix_persons_status", "persons", ["status"])
    op.create_table(
        "identity_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("numero_encrypted", sa.Text(), nullable=False),
        sa.Column("numero_hash", sa.String(length=64), nullable=False),
        sa.Column("orgao_expedidor", sa.String(length=40), nullable=True),
        sa.Column("uf_expedidor", sa.String(length=2), nullable=True),
        sa.Column("pais_emissor", sa.String(length=80), nullable=True),
        sa.Column("data_emissao", sa.Date(), nullable=True),
        sa.Column("data_validade", sa.Date(), nullable=True),
        sa.Column("principal", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_identity_documents_numero_hash", "identity_documents", ["numero_hash"])
    op.create_index("ix_identity_documents_person_id", "identity_documents", ["person_id"])
    op.create_table(
        "facial_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_encrypted", sa.Text(), nullable=False),
        sa.Column("nome_modelo", sa.String(length=120), nullable=False),
        sa.Column("versao_modelo", sa.String(length=120), nullable=False),
        sa.Column("qualidade_referencia", sa.Float(), nullable=True),
        sa.Column("imagem_referencia_path", sa.Text(), nullable=True),
        sa.Column("imagem_referencia_armazenada", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facial_references_person_id", "facial_references", ["person_id"])
    op.create_index("ix_facial_references_revogado_em", "facial_references", ["revogado_em"])
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("finalidade", sa.Text(), nullable=False),
        sa.Column("versao_termo", sa.String(length=40), nullable=False),
        sa.Column("aceito_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_records_person_id", "consent_records", ["person_id"])
    op.create_table(
        "validation_attempts",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resultado", sa.String(length=40), nullable=False),
        sa.Column("codigo_retorno", sa.String(length=60), nullable=False),
        sa.Column("similaridade_facial", sa.Float(), nullable=True),
        sa.Column("campos_avaliados", sa.Text(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("sem_imagem", sa.Boolean(), nullable=False),
        sa.Column("sem_embedding", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_validation_attempts_person_id", "validation_attempts", ["person_id"])


def downgrade() -> None:
    op.drop_table("validation_attempts")
    op.drop_table("consent_records")
    op.drop_table("facial_references")
    op.drop_table("identity_documents")
    op.drop_table("persons")
