import time
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ArkheError
from app.core.security import decrypt_text
from app.db.models import ValidationAttempt
from app.repositories.person_repository import PersonRepository
from app.schemas.datavalid import (
    CnhResult,
    DatavalidCompatibleV5Request,
    DatavalidCompatibleV5Response,
    DocumentResult,
    FaceResult,
    FieldResult,
    RegraLocal,
)
from app.services.cpf import validate_cpf
from app.services.facial import FacialService
from app.services.files import decode_base64_image
from app.services.normalization import same_date, text_similarity

DOC_CODE_TO_INTERNAL = {1: "RG", 2: "OUTRO", 3: "PASSAPORTE", 4: "OUTRO"}


@dataclass(frozen=True)
class DatavalidCompatibleV5Adapter:
    request: DatavalidCompatibleV5Request

    @property
    def internal_document_type(self) -> str | None:
        code = self.request.validacao.documento.tipo if self.request.validacao.documento else None
        return DOC_CODE_TO_INTERNAL.get(code) if code else None


class PrivateRegistryProvider:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.faces = FacialService()
        self.repo = PersonRepository(db)

    def validate_identity(self, request: DatavalidCompatibleV5Request) -> DatavalidCompatibleV5Response:
        started = time.perf_counter()
        request_id = uuid.uuid4()
        code = "ARKHE_OK"
        face_result = FaceResult(disponivel=False, codigo_retorno="ARKHE_FACE_NOT_REGISTERED")
        cpf_result = validate_cpf(request.cpf)

        if request.biometria_facial and request.biometria_facial.vivacidade:
            raise ArkheError("ARKHE_LIVENESS_NOT_SUPPORTED", "Este provedor privado nao implementa prova de vida.")
        if self.settings.require_privacy_object and request.privacidade is None:
            raise ArkheError("ARKHE_CONSENT_REQUIRED", "Objeto privacidade obrigatorio neste ambiente.")
        if not cpf_result.formato_valido or not cpf_result.digitos_verificadores_validos:
            code = "ARKHE_CPF_INVALID"

        person = self.repo.find_by_cpf(request.cpf) if code != "ARKHE_CPF_INVALID" else None
        if person is None and code != "ARKHE_CPF_INVALID":
            code = "ARKHE_PERSON_NOT_FOUND"

        if person and person.status == "bloqueado":
            code = "ARKHE_PERSON_BLOCKED"
        if person and any(cons.revogado_em for cons in person.consents):
            code = "ARKHE_CONSENT_REVOKED"

        rfb = FieldResult()
        cnh = CnhResult()
        cadastro_confirmado = False
        if person and code not in {"ARKHE_PERSON_BLOCKED", "ARKHE_CONSENT_REVOKED"}:
            validation = request.validacao
            nome_similarity = text_similarity(validation.nome, person.nome)
            mae_similarity = text_similarity(validation.nome_mae, person.nome_mae)
            pai_similarity = text_similarity(validation.nome_pai, person.nome_pai)
            rfb = FieldResult(
                nome=nome_similarity == 1.0,
                nome_similaridade=round(nome_similarity, 4),
                data_nascimento=same_date(validation.data_nascimento, person.data_nascimento),
                situacao_cpf=(validation.rfb.situacao_cpf == person.situacao_cpf_interna if validation.rfb else None),
                data_inscricao_cpf=(
                    same_date(validation.rfb.data_inscricao_cpf, person.data_inscricao_cpf)
                    if validation.rfb and validation.rfb.data_inscricao_cpf
                    else None
                ),
            )
            cnh = CnhResult(
                nome=nome_similarity == 1.0,
                nome_similaridade=round(nome_similarity, 4),
                sexo=validation.sexo == person.sexo if validation.sexo else None,
                nacionalidade=str(validation.nacionalidade) == str(person.nacionalidade) if validation.nacionalidade else None,
                nome_mae=mae_similarity == 1.0,
                nome_mae_similaridade=round(mae_similarity, 4),
                nome_pai=pai_similarity == 1.0,
                nome_pai_similaridade=round(pai_similarity, 4),
                documento=self._compare_document(request, person),
            )
            required = [
                rfb.nome,
                rfb.data_nascimento,
                cnh.sexo if cnh.sexo is not None else True,
                cnh.nacionalidade if cnh.nacionalidade is not None else True,
            ]
            cadastro_confirmado = all(required) and nome_similarity >= self.settings.text_similarity_threshold

            face_result = self._compare_face(request, person)
            if face_result.codigo_retorno != "ARKHE_FACE_OK" and code == "ARKHE_OK":
                code = face_result.codigo_retorno

        face_confirmed = bool(face_result.similaridade and face_result.similaridade >= self.settings.facial_similarity_threshold)
        response = DatavalidCompatibleV5Response(
            request_id=request_id,
            rfb_existe=person is not None,
            cnh_existe=person is not None,
            rfb=rfb,
            cnh=cnh,
            biometria_facial=face_result,
            regra_local=RegraLocal(
                cadastro_confirmado=cadastro_confirmado,
                face_confirmada=face_confirmed,
                validacao_combinada=cadastro_confirmado and face_confirmed,
                limiar_facial=self.settings.facial_similarity_threshold,
            ),
            avisos=[
                "Comparacao realizada exclusivamente com a base privada Banco Arkhe.",
                "Nenhuma base governamental foi consultada.",
                "Vivacidade nao foi verificada.",
                "O limiar facial e experimental ate calibracao local suficiente.",
            ],
        )
        self.db.add(
            ValidationAttempt(
                request_id=request_id,
                person_id=person.id if person else None,
                resultado="processado",
                codigo_retorno=code,
                similaridade_facial=face_result.similaridade,
                campos_avaliados="cpf,nome,data_nascimento,documento,biometria_facial",
                duracao_ms=int((time.perf_counter() - started) * 1000),
                sem_imagem=True,
                sem_embedding=True,
            )
        )
        return response

    def _compare_document(self, request: DatavalidCompatibleV5Request, person) -> DocumentResult:
        doc_in = request.validacao.documento
        if not doc_in:
            return DocumentResult()
        adapter = DatavalidCompatibleV5Adapter(request)
        primary = next((doc for doc in person.documents if doc.principal), person.documents[0] if person.documents else None)
        if not primary:
            return DocumentResult(tipo=False, numero=False)
        number = decrypt_text(primary.numero_encrypted)
        number_similarity = text_similarity(doc_in.numero, number)
        return DocumentResult(
            tipo=adapter.internal_document_type == primary.tipo if adapter.internal_document_type else None,
            numero=number_similarity == 1.0,
            numero_similaridade=round(number_similarity, 4),
            orgao_expedidor=doc_in.orgao_expedidor == primary.orgao_expedidor if doc_in.orgao_expedidor else None,
            uf_expedidor=doc_in.uf_expedidor == primary.uf_expedidor if doc_in.uf_expedidor else None,
        )

    def _compare_face(self, request: DatavalidCompatibleV5Request, person) -> FaceResult:
        ref = self.repo.active_facial_reference(person)
        if ref is None:
            return FaceResult(disponivel=False, codigo_retorno="ARKHE_FACE_NOT_REGISTERED")
        if not request.biometria_facial or not request.biometria_facial.imagem:
            return FaceResult(disponivel=True, codigo_retorno="ARKHE_NO_FACE")
        image = decode_base64_image(request.biometria_facial.imagem)
        probe = self.faces.generate_embedding(image)
        stored = self.faces.decrypt_embedding(ref.embedding_encrypted)
        similarity = self.faces.similarity(probe.embedding, stored)
        if similarity >= self.settings.facial_similarity_threshold:
            probability = "ALTISSIMA" if similarity >= 0.93 else "ALTA"
            return FaceResult(disponivel=True, similaridade=similarity, probabilidade=probability, codigo_retorno="ARKHE_FACE_OK")
        return FaceResult(disponivel=True, similaridade=similarity, probabilidade="BAIXA", codigo_retorno="ARKHE_FACE_MISMATCH")


class DatavalidProvider:
    """Future official provider adapter.

    This class intentionally does not call Serpro/Datavalid. It documents the
    expected replacement point for OAuth2 client credentials, official schemas,
    production endpoints, auditing and key management.
    """

    def validate_identity(self, request: DatavalidCompatibleV5Request) -> DatavalidCompatibleV5Response:
        raise NotImplementedError("DatavalidProvider e apenas um ponto de extensao documentado.")
