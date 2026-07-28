import json
import time
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ArkheError
from app.core.result_codes import RESULT_PRIORITY, IdentityResultCode
from app.core.security import decrypt_text
from app.db.models import ValidationAttempt
from app.repositories.person_repository import PersonRepository
from app.schemas.admin import DocumentType
from app.schemas.datavalid import (
    CnhResult,
    DatavalidCompatibleV5Request,
    DatavalidCompatibleV5Response,
    DocumentResult,
    FaceResult,
    FieldResult,
    RegraLocal,
)
from app.schemas.identity import (
    BiometricCheck,
    CpfCheck,
    DocumentCheck,
    IdentityChecks,
    IdentityDocumentInput,
    IdentitySelfieInput,
    IdentityValidationRequest,
    IdentityValidationResponse,
)
from app.services.consent import has_active_consent
from app.services.cpf import only_digits, validate_cpf
from app.services.facial import FacialService
from app.services.files import decode_base64_image
from app.services.normalization import same_date, text_similarity

DOC_CODE_TO_INTERNAL = {1: DocumentType.RG, 2: DocumentType.OUTRO, 3: DocumentType.PASSAPORTE, 4: DocumentType.OUTRO}


@dataclass(frozen=True)
class DatavalidCompatibleV5Adapter:
    request: DatavalidCompatibleV5Request

    @property
    def internal_document_type(self) -> DocumentType | None:
        document = self.request.validacao.documento
        return DOC_CODE_TO_INTERNAL.get(document.tipo) if document and document.tipo else None

    def to_identity_request(self) -> IdentityValidationRequest | None:
        document = self.request.validacao.documento
        face = self.request.biometria_facial
        document_type = self.internal_document_type
        if not document or not document_type or not document.numero or not face or not face.imagem:
            return None
        # The compatibility contract historically makes issuer fields optional.
        # Fill only adapter defaults needed by the stricter generic contract.
        issuer = document.orgao_expedidor
        state = document.uf_expedidor
        if document_type in {DocumentType.RG, DocumentType.CIN, DocumentType.CNH}:
            issuer = issuer or "NAO_INFORMADO"
            state = state or "NI"
        country = "BR" if document_type == DocumentType.PASSAPORTE else None
        return IdentityValidationRequest(
            cpf=self.request.cpf,
            documento=IdentityDocumentInput(
                tipo=document_type,
                numero=document.numero,
                orgao_expedidor=issuer,
                uf_expedidor=state,
                pais_emissor=country,
            ),
            selfie=IdentitySelfieInput(imagem_base64=face.imagem),
        )


@dataclass
class DocumentEvaluation:
    check: DocumentCheck
    code: IdentityResultCode | None
    reasons: list[str]


class IdentityValidationService:
    """Central policy for CPF + official document + facial reference validation."""

    def __init__(self, db: Session, facial_service: FacialService | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.faces = facial_service or FacialService()
        self.repo = PersonRepository(db)

    def validate(self, request: IdentityValidationRequest) -> IdentityValidationResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4()
        failures: list[IdentityResultCode] = []
        reasons: list[str] = []
        person = None
        similarity = None
        image_supplied = bool(request.selfie.imagem_base64)
        reference_missing = True

        cpf_validation = validate_cpf(request.cpf)
        cpf_valid = cpf_validation.formato_valido and cpf_validation.digitos_verificadores_validos
        if not cpf_valid:
            failures.append(IdentityResultCode.CPF_INVALIDO)
            reasons.append("CPF_INVALIDO")
        else:
            person = self.repo.find_by_cpf(request.cpf)
            if person is None:
                failures.append(IdentityResultCode.PESSOA_NAO_ENCONTRADA)
                reasons.append("PESSOA_NAO_ENCONTRADA")
            elif person.status != "ativo":
                failures.append(IdentityResultCode.PESSOA_INATIVA)
                reasons.append("PESSOA_INATIVA")
            elif not has_active_consent(person):
                failures.append(IdentityResultCode.CONSENTIMENTO_AUSENTE)
                reasons.append("CONSENTIMENTO_AUSENTE")

        document_evaluation = DocumentEvaluation(
            check=DocumentCheck(valido=False, tipo=request.documento.tipo, campos={}),
            code=None,
            reasons=[],
        )
        biometric = BiometricCheck(
            valido=False,
            similaridade=None,
            limiar=self.settings.facial_similarity_threshold,
        )

        reference = self.repo.active_facial_reference(person) if person else None
        reference_missing = reference is None
        can_validate = person is not None and person.status == "ativo" and has_active_consent(person)
        if can_validate:
            document_evaluation = self._compare_document(request.documento, person, request.cpf)
            if document_evaluation.code:
                failures.append(document_evaluation.code)
                reasons.extend(document_evaluation.reasons)

            if reference is None:
                failures.append(IdentityResultCode.REFERENCIA_FACIAL_AUSENTE)
                reasons.append("REFERENCIA_FACIAL_AUSENTE")
            else:
                try:
                    probe_image = decode_base64_image(request.selfie.imagem_base64)
                    probe = self.faces.generate_embedding(probe_image)
                    stored = self.faces.decrypt_embedding(reference.embedding_encrypted)
                    similarity = self.faces.similarity(probe.embedding, stored)
                    biometric = BiometricCheck(
                        valido=similarity >= self.settings.facial_similarity_threshold,
                        similaridade=similarity,
                        limiar=self.settings.facial_similarity_threshold,
                    )
                    if not biometric.valido:
                        failures.append(IdentityResultCode.BIOMETRIA_NAO_CONFIRMADA)
                        reasons.append("BIOMETRIA_ABAIXO_DO_LIMIAR")
                except ArkheError as exc:
                    mapped = self._map_face_error(exc.code)
                    failures.append(mapped)
                    reasons.append(mapped.value)
                except Exception:
                    failures.append(IdentityResultCode.ERRO_INTERNO)
                    reasons.append("ERRO_INTERNO")

        code = self._primary_code(failures)
        valid = not failures and document_evaluation.check.valido and biometric.valido
        if valid:
            code = IdentityResultCode.IDENTIDADE_CONFIRMADA

        response = IdentityValidationResponse(
            request_id=request_id,
            valido=valid,
            codigo=code,
            motivos=list(dict.fromkeys(reasons)),
            verificacoes=IdentityChecks(
                cpf=CpfCheck(valido=cpf_valid, pessoa_encontrada=person is not None),
                documento=document_evaluation.check,
                biometria=biometric,
            ),
        )
        self._audit(
            response=response,
            person_id=person.id if person else None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            image_supplied=image_supplied,
            reference_missing=reference_missing,
        )
        return response

    def _compare_document(
        self,
        supplied: IdentityDocumentInput,
        person,
        cpf: str,
    ) -> DocumentEvaluation:
        same_type = [
            document
            for document in person.documents
            if document.tipo.strip().upper() == supplied.tipo.value
        ]
        if not same_type:
            return DocumentEvaluation(
                DocumentCheck(valido=False, tipo=supplied.tipo, campos={"tipo": False}),
                IdentityResultCode.DOCUMENTO_NAO_ENCONTRADO,
                ["TIPO_DOCUMENTO_NAO_ENCONTRADO"],
            )

        supplied_number = self.repo.normalize_document_value(supplied.numero)
        document = next(
            (
                candidate
                for candidate in same_type
                if self.repo.normalize_document_value(decrypt_text(candidate.numero_encrypted)) == supplied_number
            ),
            next((candidate for candidate in same_type if candidate.principal), same_type[0]),
        )
        stored_number = self.repo.normalize_document_value(decrypt_text(document.numero_encrypted))
        fields: dict[str, bool] = {"tipo": True, "numero": supplied_number == stored_number}
        reasons: list[str] = []
        if supplied.tipo == DocumentType.CIN and only_digits(supplied.numero) != only_digits(cpf):
            fields["numero"] = False
        if not fields["numero"]:
            reasons.append("NUMERO_DOCUMENTO_DIVERGENTE")

        comparisons = {
            "orgao_expedidor": (
                self.repo.normalize_document_text(supplied.orgao_expedidor),
                self.repo.normalize_document_text(document.orgao_expedidor),
            ),
            "uf_expedidor": (
                self.repo.normalize_document_text(supplied.uf_expedidor),
                self.repo.normalize_document_text(document.uf_expedidor),
            ),
            "pais_emissor": (
                self.repo.normalize_document_text(supplied.pais_emissor),
                self.repo.normalize_document_text(document.pais_emissor),
            ),
        }
        for field, (incoming, stored) in comparisons.items():
            if incoming is not None:
                fields[field] = incoming == stored
                if not fields[field]:
                    reasons.append(f"{field.upper()}_DIVERGENTE")

        if supplied.data_emissao is not None:
            fields["data_emissao"] = supplied.data_emissao == document.data_emissao
            if not fields["data_emissao"]:
                reasons.append("DATA_EMISSAO_DIVERGENTE")

        expired = document.data_validade is not None and document.data_validade < date.today()
        if document.data_validade is not None:
            fields["data_validade"] = not expired and (
                supplied.data_validade is None or supplied.data_validade == document.data_validade
            )
            if expired:
                reasons.append("DOCUMENTO_VENCIDO")
            elif not fields["data_validade"]:
                reasons.append("DATA_VALIDADE_DIVERGENTE")

        valid = all(fields.values()) and not expired
        code = None
        if expired:
            code = IdentityResultCode.DOCUMENTO_VENCIDO
        elif not valid:
            code = IdentityResultCode.DOCUMENTO_DIVERGENTE
        return DocumentEvaluation(
            check=DocumentCheck(valido=valid, tipo=supplied.tipo, campos=fields),
            code=code,
            reasons=reasons,
        )

    @staticmethod
    def _map_face_error(code: str) -> IdentityResultCode:
        if code == "ARKHE_NO_FACE":
            return IdentityResultCode.FACE_NAO_DETECTADA
        if code == "ARKHE_MULTIPLE_FACES":
            return IdentityResultCode.MULTIPLAS_FACES_DETECTADAS
        return IdentityResultCode.SELFIE_INVALIDA

    @staticmethod
    def _primary_code(failures: list[IdentityResultCode]) -> IdentityResultCode:
        return next((code for code in RESULT_PRIORITY if code in failures), IdentityResultCode.ERRO_INTERNO)

    def _audit(
        self,
        response: IdentityValidationResponse,
        person_id,
        duration_ms: int,
        image_supplied: bool,
        reference_missing: bool,
    ) -> None:
        evaluated = {
            "documento_confirmado": response.verificacoes.documento.valido,
            "campos": response.verificacoes.documento.campos,
            "motivos": response.motivos,
        }
        self.db.add(
            ValidationAttempt(
                request_id=response.request_id,
                person_id=person_id,
                resultado="aprovado" if response.valido else "reprovado",
                codigo_retorno=response.codigo.value,
                similaridade_facial=response.verificacoes.biometria.similaridade,
                campos_avaliados=json.dumps(evaluated, ensure_ascii=True),
                duracao_ms=duration_ms,
                sem_imagem=not image_supplied,
                sem_embedding=reference_missing,
            )
        )


class PrivateRegistryProvider:
    """Compatibility provider backed by the same policy as the generic API."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.core = IdentityValidationService(db)
        self.repo = PersonRepository(db)

    def validate_identity(self, request: DatavalidCompatibleV5Request) -> DatavalidCompatibleV5Response:
        if request.biometria_facial and request.biometria_facial.vivacidade:
            raise ArkheError("ARKHE_LIVENESS_NOT_SUPPORTED", "Este provedor privado nao implementa prova de vida.")
        if self.settings.require_privacy_object and request.privacidade is None:
            raise ArkheError("ARKHE_CONSENT_REQUIRED", "Objeto privacidade obrigatorio neste ambiente.")

        adapter = DatavalidCompatibleV5Adapter(request)
        generic_request = adapter.to_identity_request()
        if generic_request is None:
            raise ArkheError("ARKHE_INVALID_REQUEST", "Documento e biometria facial sao obrigatorios.")
        generic = self.core.validate(generic_request)
        compatibility_errors = {
            IdentityResultCode.SELFIE_INVALIDA: (
                "ARKHE_UNSUPPORTED_IMAGE",
                "Imagem Base64 invalida.",
            ),
            IdentityResultCode.FACE_NAO_DETECTADA: (
                "ARKHE_NO_FACE",
                "Nenhuma face detectada.",
            ),
            IdentityResultCode.MULTIPLAS_FACES_DETECTADAS: (
                "ARKHE_MULTIPLE_FACES",
                "Mais de uma face detectada.",
            ),
        }
        if generic.codigo in compatibility_errors:
            error_code, message = compatibility_errors[generic.codigo]
            raise ArkheError(error_code, message)

        person = self.repo.find_by_cpf(request.cpf) if generic.verificacoes.cpf.valido else None
        rfb = FieldResult()
        cnh = CnhResult()
        civil_confirmed = False
        if person:
            validation = request.validacao
            name_similarity = text_similarity(validation.nome, person.nome)
            mother_similarity = text_similarity(validation.nome_mae, person.nome_mae)
            father_similarity = text_similarity(validation.nome_pai, person.nome_pai)
            rfb = FieldResult(
                nome=name_similarity == 1.0,
                nome_similaridade=round(name_similarity, 4),
                data_nascimento=same_date(validation.data_nascimento, person.data_nascimento),
                situacao_cpf=(validation.rfb.situacao_cpf == person.situacao_cpf_interna if validation.rfb else None),
                data_inscricao_cpf=(
                    same_date(validation.rfb.data_inscricao_cpf, person.data_inscricao_cpf)
                    if validation.rfb and validation.rfb.data_inscricao_cpf
                    else None
                ),
            )
            document_fields = generic.verificacoes.documento.campos
            cnh = CnhResult(
                nome=name_similarity == 1.0,
                nome_similaridade=round(name_similarity, 4),
                sexo=validation.sexo == person.sexo if validation.sexo else None,
                nacionalidade=str(validation.nacionalidade) == str(person.nacionalidade) if validation.nacionalidade else None,
                nome_mae=mother_similarity == 1.0,
                nome_mae_similaridade=round(mother_similarity, 4),
                nome_pai=father_similarity == 1.0,
                nome_pai_similaridade=round(father_similarity, 4),
                documento=DocumentResult(
                    tipo=document_fields.get("tipo"),
                    numero=document_fields.get("numero"),
                    numero_similaridade=1.0 if document_fields.get("numero") else 0.0,
                    orgao_expedidor=document_fields.get("orgao_expedidor"),
                    uf_expedidor=document_fields.get("uf_expedidor"),
                ),
            )
            civil_confirmed = all(
                [
                    rfb.nome,
                    rfb.data_nascimento,
                    cnh.sexo if cnh.sexo is not None else True,
                    cnh.nacionalidade if cnh.nacionalidade is not None else True,
                ]
            )

        biometric = generic.verificacoes.biometria
        face_result = FaceResult(
            disponivel=generic.codigo != IdentityResultCode.REFERENCIA_FACIAL_AUSENTE,
            similaridade=biometric.similaridade,
            probabilidade=(
                "ALTISSIMA"
                if biometric.similaridade is not None and biometric.similaridade >= 0.93
                else "ALTA" if biometric.valido else "BAIXA"
            ),
            codigo_retorno=(
                "ARKHE_FACE_OK"
                if biometric.valido
                else "ARKHE_FACE_NOT_REGISTERED"
                if generic.codigo == IdentityResultCode.REFERENCIA_FACIAL_AUSENTE
                else "ARKHE_FACE_MISMATCH"
            ),
        )
        combined = generic.valido and civil_confirmed
        return DatavalidCompatibleV5Response(
            request_id=generic.request_id,
            rfb_existe=person is not None,
            cnh_existe=person is not None,
            rfb=rfb,
            cnh=cnh,
            biometria_facial=face_result,
            regra_local=RegraLocal(
                cadastro_confirmado=civil_confirmed and generic.verificacoes.documento.valido,
                face_confirmada=biometric.valido,
                validacao_combinada=combined,
                limiar_facial=self.settings.facial_similarity_threshold,
            ),
            avisos=[
                "Comparacao realizada exclusivamente com uma base privada.",
                "Nenhuma base governamental foi consultada.",
                "Esta camada nao e uma integracao oficial com Datavalid.",
                "Vivacidade nao foi verificada.",
            ],
        )


class DatavalidProvider:
    """Future official provider adapter; no governmental service is called."""

    def validate_identity(self, request: DatavalidCompatibleV5Request) -> DatavalidCompatibleV5Response:
        raise NotImplementedError("DatavalidProvider e apenas um ponto de extensao documentado.")
