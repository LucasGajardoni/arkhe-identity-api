from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_api_key
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.result_codes import IdentityResultCode
from app.schemas.identity import IdentityValidationRequest, IdentityValidationResponse
from app.services.validation import IdentityValidationService

router = APIRouter(prefix="/v1/identity", tags=["identity"])


@router.post(
    "/validate",
    response_model=IdentityValidationResponse,
    summary="Validar identidade em uma base privada",
    description=(
        "Valida CPF, documento oficial e selfie contra uma referência facial privada. "
        "Requer X-Arkhe-Api-Key. Não realiza prova de vida, não consulta bases "
        "governamentais e não é uma integração oficial com Datavalid."
    ),
    responses={
        200: {
            "description": "Validação processada, aprovada ou reprovada.",
            "content": {
                "application/json": {
                    "examples": {
                        "aprovada": {
                            "summary": "Identidade confirmada",
                            "value": {
                                "request_id": "3bc63ac8-a063-4608-a490-78bd187e78d1",
                                "valido": True,
                                "codigo": "IDENTIDADE_CONFIRMADA",
                                "motivos": [],
                                "verificacoes": {
                                    "cpf": {"valido": True, "pessoa_encontrada": True},
                                    "documento": {
                                        "valido": True,
                                        "tipo": "RG",
                                        "campos": {"tipo": True, "numero": True},
                                    },
                                    "biometria": {
                                        "valido": True,
                                        "similaridade": 0.94,
                                        "limiar": 0.85,
                                    },
                                },
                            },
                        },
                        "reprovada": {
                            "summary": "Documento divergente",
                            "value": {
                                "request_id": "c2a76f67-377f-4d25-b19d-6e981e416336",
                                "valido": False,
                                "codigo": "DOCUMENTO_DIVERGENTE",
                                "motivos": ["NUMERO_DOCUMENTO_DIVERGENTE"],
                                "verificacoes": {
                                    "cpf": {"valido": True, "pessoa_encontrada": True},
                                    "documento": {
                                        "valido": False,
                                        "tipo": "RG",
                                        "campos": {"tipo": True, "numero": False},
                                    },
                                    "biometria": {
                                        "valido": True,
                                        "similaridade": 0.92,
                                        "limiar": 0.85,
                                    },
                                },
                            },
                        },
                    }
                }
            },
        },
        400: {"description": "CPF ou selfie inválida; a resposta mantém o contrato estruturado."},
        401: {"description": "API key ausente ou inválida."},
        422: {"description": "Payload estruturalmente inválido."},
    },
)
@limiter.limit(get_settings().identity_validation_rate_limit)
def validate_identity(
    payload: IdentityValidationRequest,
    request: Request,
    response: Response,
    _: None = Depends(require_api_key),
    db: Session = Depends(db_session),
) -> IdentityValidationResponse:
    result = IdentityValidationService(db).validate(payload)
    db.commit()
    if result.codigo in {
        IdentityResultCode.CPF_INVALIDO,
        IdentityResultCode.SELFIE_INVALIDA,
        IdentityResultCode.FACE_NAO_DETECTADA,
        IdentityResultCode.MULTIPLAS_FACES_DETECTADAS,
    }:
        response.status_code = status.HTTP_400_BAD_REQUEST
    elif result.codigo == IdentityResultCode.ERRO_INTERNO:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return result
