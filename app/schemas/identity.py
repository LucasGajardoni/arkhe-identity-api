from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.result_codes import IdentityResultCode
from app.schemas.admin import DocumentType


class IdentityDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: DocumentType
    numero: str = Field(min_length=1)
    orgao_expedidor: str | None = None
    uf_expedidor: str | None = None
    pais_emissor: str | None = None
    data_emissao: date | None = None
    data_validade: date | None = None

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
            if not self.orgao_expedidor or not self.uf_expedidor:
                raise ValueError(f"Órgão e UF expedidores são obrigatórios para {self.tipo.value}.")
        if self.tipo == DocumentType.PASSAPORTE and not self.pais_emissor:
            raise ValueError("País emissor é obrigatório para PASSAPORTE.")
        if self.tipo == DocumentType.CRNM and not (self.pais_emissor or self.orgao_expedidor):
            raise ValueError("País emissor ou órgão expedidor é obrigatório para CRNM.")
        return self


class IdentitySelfieInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imagem_base64: str = Field(min_length=1)


class IdentityValidationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "cpf": "52998224725",
                "documento": {
                    "tipo": "RG",
                    "numero": "123456789",
                    "orgao_expedidor": "SSP",
                    "uf_expedidor": "SP",
                },
                "selfie": {"imagem_base64": "<BASE64>"},
            }
        },
    )

    cpf: str
    documento: IdentityDocumentInput
    selfie: IdentitySelfieInput


class CpfCheck(BaseModel):
    valido: bool
    pessoa_encontrada: bool


class DocumentCheck(BaseModel):
    valido: bool
    tipo: DocumentType
    campos: dict[str, bool] = Field(default_factory=dict)


class BiometricCheck(BaseModel):
    valido: bool
    similaridade: float | None = None
    limiar: float


class IdentityChecks(BaseModel):
    cpf: CpfCheck
    documento: DocumentCheck
    biometria: BiometricCheck


class IdentityValidationResponse(BaseModel):
    request_id: UUID
    valido: bool
    codigo: IdentityResultCode
    motivos: list[str] = Field(default_factory=list)
    verificacoes: IdentityChecks
