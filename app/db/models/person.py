import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cpf_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cpf_encrypted: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(String(255), index=True)
    nome_social: Mapped[str | None] = mapped_column(String(255))
    data_nascimento: Mapped[date] = mapped_column(Date)
    sexo: Mapped[str] = mapped_column(String(1))
    nacionalidade: Mapped[str] = mapped_column(String(40), default="1")
    nome_mae: Mapped[str | None] = mapped_column(String(255))
    nome_pai: Mapped[str | None] = mapped_column(String(255))
    situacao_cpf_interna: Mapped[str] = mapped_column(String(40), default="regular")
    data_inscricao_cpf: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="ativo", index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    consentimento_aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    versao_termo_consentimento: Mapped[str | None] = mapped_column(String(40))
    finalidade_consentimento: Mapped[str | None] = mapped_column(Text)
    exclusao_solicitada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list["IdentityDocument"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    facial_references: Mapped[list["FacialReference"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    consents: Mapped[list["ConsentRecord"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class IdentityDocument(Base):
    __tablename__ = "identity_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    numero_encrypted: Mapped[str] = mapped_column(Text)
    numero_hash: Mapped[str] = mapped_column(String(64), index=True)
    orgao_expedidor: Mapped[str | None] = mapped_column(String(40))
    uf_expedidor: Mapped[str | None] = mapped_column(String(2))
    pais_emissor: Mapped[str | None] = mapped_column(String(80))
    data_emissao: Mapped[date | None] = mapped_column(Date)
    data_validade: Mapped[date | None] = mapped_column(Date)
    principal: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    person: Mapped[Person] = relationship(back_populates="documents")


class FacialReference(Base):
    __tablename__ = "facial_references"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    embedding_encrypted: Mapped[str] = mapped_column(Text)
    nome_modelo: Mapped[str] = mapped_column(String(120))
    versao_modelo: Mapped[str] = mapped_column(String(120))
    qualidade_referencia: Mapped[float | None]
    imagem_referencia_path: Mapped[str | None] = mapped_column(Text)
    imagem_referencia_armazenada: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    person: Mapped[Person] = relationship(back_populates="facial_references")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    finalidade: Mapped[str] = mapped_column(Text)
    versao_termo: Mapped[str] = mapped_column(String(40))
    aceito_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    person: Mapped[Person] = relationship(back_populates="consents")


class ValidationAttempt(Base):
    __tablename__ = "validation_attempts"

    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resultado: Mapped[str] = mapped_column(String(40))
    codigo_retorno: Mapped[str] = mapped_column(String(60))
    similaridade_facial: Mapped[float | None]
    campos_avaliados: Mapped[str | None] = mapped_column(Text)
    duracao_ms: Mapped[int | None]
    sem_imagem: Mapped[bool] = mapped_column(Boolean, default=True)
    sem_embedding: Mapped[bool] = mapped_column(Boolean, default=True)
