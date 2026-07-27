from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ConsentInput(BaseModel):
    consentimento_aceito: bool = Field(default=False)
    versao_termo: str = "arkhe-consent-v1"
    finalidade: str = "Prova de conceito academica privada Banco Arkhe"


class PersonCreate(BaseModel):
    cpf: str
    nome: str
    nome_social: str | None = None
    data_nascimento: date
    sexo: str
    nacionalidade: str = "1"
    nome_mae: str | None = None
    nome_pai: str | None = None
    situacao_cpf_interna: str = "regular"
    data_inscricao_cpf: date | None = None
    email: EmailStr | None = None
    telefone: str | None = None
    status: str = "ativo"
    consentimento: ConsentInput


class PersonUpdate(BaseModel):
    nome: str | None = None
    nome_social: str | None = None
    email: EmailStr | None = None
    telefone: str | None = None
    status: str | None = None
    exclusao_solicitada_em: datetime | None = None


class DocumentCreate(BaseModel):
    tipo: str
    numero: str
    orgao_expedidor: str | None = None
    uf_expedidor: str | None = None
    pais_emissor: str | None = "BR"
    data_emissao: date | None = None
    data_validade: date | None = None
    principal: bool = True


class PersonListItem(BaseModel):
    id: UUID
    cpf_mascarado: str
    nome: str
    status: str
    criado_em: datetime
    possui_biometria: bool


class FacialReferenceInput(BaseModel):
    imagem_base64: str


class LoginInput(BaseModel):
    username: str
    password: str


class TokenOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
