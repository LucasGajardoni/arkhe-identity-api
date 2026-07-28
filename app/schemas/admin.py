from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.cpf import only_digits, validate_cpf


class DocumentType(StrEnum):
    RG = "RG"
    CIN = "CIN"
    CNH = "CNH"
    PASSAPORTE = "PASSAPORTE"
    CRNM = "CRNM"
    OUTRO = "OUTRO"


class ConsentInput(BaseModel):
    consentimento_aceito: bool = Field(default=False)
    versao_termo: str = "arkhe-consent-v1"
    finalidade: str = "Prova de conceito academica privada Banco Arkhe"


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    status: str = "ativo"
    consentimento: ConsentInput

    @field_validator("cpf")
    @classmethod
    def validate_person_cpf(cls, value: str) -> str:
        normalized = only_digits(value)
        result = validate_cpf(normalized)
        if not result.formato_valido or not result.digitos_verificadores_validos:
            raise ValueError("CPF inválido.")
        return normalized


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None = None
    nome_social: str | None = None
    status: str | None = None
    exclusao_solicitada_em: datetime | None = None


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: DocumentType
    numero: str
    orgao_expedidor: str | None = None
    uf_expedidor: str | None = None
    pais_emissor: str | None = None
    data_emissao: date | None = None
    data_validade: date | None = None
    principal: bool = True

    @field_validator("numero")
    @classmethod
    def normalize_number(cls, value: str) -> str:
        normalized = "".join(character for character in value.strip().upper() if character.isalnum())
        if not normalized:
            raise ValueError("Número do documento é obrigatório.")
        return normalized

    @field_validator("orgao_expedidor", "uf_expedidor", "pais_emissor")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip().upper() if value and value.strip() else None

    @model_validator(mode="after")
    def validate_fields_by_type(self):
        if self.tipo in {DocumentType.RG, DocumentType.CIN, DocumentType.CNH}:
            if not self.orgao_expedidor:
                raise ValueError(f"Órgão expedidor é obrigatório para {self.tipo.value}.")
            if not self.uf_expedidor:
                raise ValueError(f"UF expedidora é obrigatória para {self.tipo.value}.")
        if self.tipo == DocumentType.PASSAPORTE and not self.pais_emissor:
            raise ValueError("País emissor é obrigatório para PASSAPORTE.")
        if self.tipo == DocumentType.CRNM and not (self.pais_emissor or self.orgao_expedidor):
            raise ValueError("País emissor ou órgão expedidor é obrigatório para CRNM.")
        return self


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
