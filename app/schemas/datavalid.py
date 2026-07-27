from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class PrivacyRfb(BaseModel):
    id_template: str | None = None


class PrivacySenatran(BaseModel):
    token: str | None = None
    cnpj_anuente: str | None = None


class PrivacyObject(BaseModel):
    rfb: PrivacyRfb | None = None
    senatran: PrivacySenatran | None = None


class RfbValidation(BaseModel):
    situacao_cpf: str | None = None
    data_inscricao_cpf: date | None = None


class DocumentoValidation(BaseModel):
    tipo: int | None = None
    numero: str | None = None
    orgao_expedidor: str | None = None
    uf_expedidor: str | None = None


class EnderecoValidation(BaseModel):
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cep: str | None = None
    municipio: str | None = None
    uf: str | None = None


class PessoaValidation(BaseModel):
    nome: str | None = None
    nome_social: str | None = None
    data_nascimento: date | None = None
    sexo: str | None = None
    nacionalidade: int | None = None
    nome_mae: str | None = None
    nome_pai: str | None = None
    rfb: RfbValidation | None = None
    documento: DocumentoValidation | None = None
    endereco: EnderecoValidation | None = None


class BiometriaFacialInput(BaseModel):
    imagem: str | None = None
    vivacidade: bool = False


class DatavalidCompatibleV5Request(BaseModel):
    privacidade: PrivacyObject | None = None
    cpf: str
    validacao: PessoaValidation
    biometria_facial: BiometriaFacialInput | None = None
    tag: str | None = None


class FieldResult(BaseModel):
    nome: bool | None = None
    nome_similaridade: float | None = None
    data_nascimento: bool | None = None
    situacao_cpf: bool | None = None
    data_inscricao_cpf: bool | None = None


class DocumentResult(BaseModel):
    tipo: bool | None = None
    numero: bool | None = None
    numero_similaridade: float | None = None
    orgao_expedidor: bool | None = None
    uf_expedidor: bool | None = None


class CnhResult(BaseModel):
    nome: bool | None = None
    nome_similaridade: float | None = None
    sexo: bool | None = None
    nacionalidade: bool | None = None
    nome_mae: bool | None = None
    nome_mae_similaridade: float | None = None
    nome_pai: bool | None = None
    nome_pai_similaridade: float | None = None
    documento: DocumentResult = Field(default_factory=DocumentResult)


class FaceResult(BaseModel):
    disponivel: bool
    similaridade: float | None = None
    probabilidade: str | None = None
    vivacidade: None = None
    codigo_retorno: str


class RegraLocal(BaseModel):
    cadastro_confirmado: bool
    face_confirmada: bool
    validacao_combinada: bool
    limiar_facial: float


class DatavalidCompatibleV5Response(BaseModel):
    request_id: UUID
    provedor: str = "ARKHE_PRIVATE_REGISTRY"
    ambiente: str = "TCC"
    rfb_existe: bool
    cnh_existe: bool
    rfb: FieldResult
    cnh: CnhResult
    biometria_facial: FaceResult
    regra_local: RegraLocal
    avisos: list[str]
