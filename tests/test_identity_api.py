import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ConsentRecord, FacialReference, ValidationAttempt
from app.repositories.person_repository import PersonRepository
from app.schemas.admin import ConsentInput, DocumentCreate, PersonCreate
from app.services.facial import FacialService
from app.services.files import decode_base64_image
from tests.conftest import synthetic_face

API_HEADERS = {"X-Arkhe-Api-Key": "test-key"}


def seed_identity(
    db: Session,
    *,
    document_type: str = "RG",
    document_number: str = "123456789",
    with_document: bool = True,
    with_face: bool = True,
    status: str = "ativo",
    consent: bool = True,
):
    repo = PersonRepository(db)
    person = repo.create_person(
        PersonCreate(
            cpf="52998224725",
            nome="Pessoa Teste",
            data_nascimento=date(2000, 1, 1),
            sexo="O",
            status=status,
            consentimento=ConsentInput(consentimento_aceito=consent),
        )
    )
    if with_document:
        kwargs = {
            "tipo": document_type,
            "numero": document_number,
            "orgao_expedidor": "SSP" if document_type != "PASSAPORTE" else None,
            "uf_expedidor": "SP" if document_type in {"RG", "CIN", "CNH"} else None,
            "pais_emissor": "BR",
        }
        repo.add_document(person, DocumentCreate(**kwargs))
    if with_face:
        service = FacialService()
        embedding = service.generate_embedding(decode_base64_image(synthetic_face())).embedding
        db.add(
            FacialReference(
                person_id=person.id,
                embedding_encrypted=service.encrypt_embedding(embedding),
                nome_modelo="fake",
                versao_modelo="test",
                qualidade_referencia=0.9,
                imagem_referencia_armazenada=False,
            )
        )
    db.commit()
    return person


def identity_payload(**document_overrides):
    document = {
        "tipo": "RG",
        "numero": "123456789",
        "orgao_expedidor": "SSP",
        "uf_expedidor": "SP",
    }
    document.update(document_overrides)
    return {
        "cpf": "52998224725",
        "documento": document,
        "selfie": {"imagem_base64": synthetic_face()},
    }


def test_completely_valid_identity(client: TestClient, db: Session):
    seed_identity(db)
    response = client.post("/v1/identity/validate", json=identity_payload(), headers=API_HEADERS)
    data = response.json()
    assert response.status_code == 200
    assert data["valido"] is True
    assert data["codigo"] == "IDENTIDADE_CONFIRMADA"
    assert data["verificacoes"]["documento"]["valido"] is True
    assert "person_id" not in response.text
    assert "52998224725" not in response.text


def test_person_not_found_is_non_enumerating_200(client: TestClient):
    response = client.post("/v1/identity/validate", json=identity_payload(), headers=API_HEADERS)
    assert response.status_code == 200
    assert response.json()["codigo"] == "PESSOA_NAO_ENCONTRADA"


def test_invalid_cpf_returns_structured_400(client: TestClient):
    payload = identity_payload()
    payload["cpf"] = "11111111111"
    response = client.post("/v1/identity/validate", json=payload, headers=API_HEADERS)
    assert response.status_code == 400
    assert response.json()["codigo"] == "CPF_INVALIDO"


def test_document_not_found_and_type_mismatch(client: TestClient, db: Session):
    seed_identity(db)
    response = client.post(
        "/v1/identity/validate",
        json=identity_payload(tipo="CNH"),
        headers=API_HEADERS,
    )
    assert response.json()["codigo"] == "DOCUMENTO_NAO_ENCONTRADO"


def test_document_field_divergences(client: TestClient, db: Session):
    seed_identity(db)
    cases = [
        ({"numero": "999"}, "NUMERO_DOCUMENTO_DIVERGENTE"),
        ({"orgao_expedidor": "DETRAN"}, "ORGAO_EXPEDIDOR_DIVERGENTE"),
        ({"uf_expedidor": "RJ"}, "UF_EXPEDIDOR_DIVERGENTE"),
    ]
    for overrides, reason in cases:
        data = client.post(
            "/v1/identity/validate",
            json=identity_payload(**overrides),
            headers=API_HEADERS,
        ).json()
        assert data["codigo"] == "DOCUMENTO_DIVERGENTE"
        assert reason in data["motivos"]


def test_sent_optional_field_must_match_even_when_not_stored(
    client: TestClient,
    db: Session,
):
    person = seed_identity(db)
    person.documents[0].pais_emissor = None
    db.commit()
    data = client.post(
        "/v1/identity/validate",
        json=identity_payload(pais_emissor="BR"),
        headers=API_HEADERS,
    ).json()
    assert data["codigo"] == "DOCUMENTO_DIVERGENTE"
    assert data["verificacoes"]["documento"]["campos"]["pais_emissor"] is False


def test_legacy_cin_number_must_still_match_cpf(client: TestClient, db: Session):
    seed_identity(db, document_type="CIN", document_number="12345678900")
    data = client.post(
        "/v1/identity/validate",
        json=identity_payload(
            tipo="CIN",
            numero="12345678900",
            orgao_expedidor="SSP",
            uf_expedidor="SP",
        ),
        headers=API_HEADERS,
    ).json()
    assert data["codigo"] == "DOCUMENTO_DIVERGENTE"
    assert data["verificacoes"]["documento"]["campos"]["numero"] is False


def test_expired_document(client: TestClient, db: Session):
    person = seed_identity(db)
    person.documents[0].data_validade = date.today() - timedelta(days=1)
    db.commit()
    data = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()
    assert data["codigo"] == "DOCUMENTO_VENCIDO"


def test_rg_without_expiration_is_valid(client: TestClient, db: Session):
    seed_identity(db)
    assert client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()["valido"] is True


def test_missing_face_reference(client: TestClient, db: Session):
    seed_identity(db, with_face=False)
    data = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()
    assert data["codigo"] == "REFERENCIA_FACIAL_AUSENTE"


def test_invalid_selfie(client: TestClient, db: Session):
    seed_identity(db)
    payload = identity_payload()
    payload["selfie"]["imagem_base64"] = "not-base64"
    response = client.post("/v1/identity/validate", json=payload, headers=API_HEADERS)
    assert response.status_code == 400
    assert response.json()["codigo"] == "SELFIE_INVALIDA"


def test_biometry_above_and_below_threshold(client: TestClient, db: Session, monkeypatch):
    seed_identity(db)
    monkeypatch.setattr(FacialService, "similarity", lambda *_: 0.99)
    good = client.post("/v1/identity/validate", json=identity_payload(), headers=API_HEADERS).json()
    monkeypatch.setattr(FacialService, "similarity", lambda *_: 0.1)
    bad = client.post("/v1/identity/validate", json=identity_payload(), headers=API_HEADERS).json()
    assert good["valido"] is True
    assert bad["codigo"] == "BIOMETRIA_NAO_CONFIRMADA"


def test_document_and_biometry_are_both_mandatory(client: TestClient, db: Session, monkeypatch):
    seed_identity(db)
    monkeypatch.setattr(FacialService, "similarity", lambda *_: 0.99)
    wrong_document = client.post(
        "/v1/identity/validate",
        json=identity_payload(numero="999"),
        headers=API_HEADERS,
    ).json()
    monkeypatch.setattr(FacialService, "similarity", lambda *_: 0.1)
    wrong_face = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()
    assert wrong_document["verificacoes"]["biometria"]["valido"] is True
    assert wrong_document["valido"] is False
    assert wrong_face["verificacoes"]["documento"]["valido"] is True
    assert wrong_face["valido"] is False


def test_revoked_and_renewed_consent(client: TestClient, db: Session):
    person = seed_identity(db)
    for consent in person.consents:
        consent.revogado_em = datetime.now(UTC)
    db.commit()
    revoked = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()
    db.add(
        ConsentRecord(
            person_id=person.id,
            finalidade="Prova de conceito academica privada Banco Arkhe",
            versao_termo="v2",
        )
    )
    db.commit()
    renewed = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()
    assert revoked["codigo"] == "CONSENTIMENTO_AUSENTE"
    assert renewed["valido"] is True


def test_consent_never_given(client: TestClient, db: Session):
    seed_identity(db, consent=False)
    data = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    ).json()
    assert data["codigo"] == "CONSENTIMENTO_AUSENTE"


def test_email_phone_are_not_accepted_or_used(client: TestClient, db: Session):
    seed_identity(db)
    payload = identity_payload()
    payload["email"] = "x@example.test"
    payload["telefone"] = "11999999999"
    response = client.post("/v1/identity/validate", json=payload, headers=API_HEADERS)
    assert response.status_code == 422


def test_v5_still_uses_central_document_policy(client: TestClient, db: Session):
    seed_identity(db)
    payload = {
        "cpf": "52998224725",
        "validacao": {
            "nome": "Pessoa Teste",
            "data_nascimento": "2000-01-01",
            "documento": {
                "tipo": 1,
                "numero": "999",
                "orgao_expedidor": "SSP",
                "uf_expedidor": "SP",
            },
        },
        "biometria_facial": {"imagem": synthetic_face(), "vivacidade": False},
    }
    response = client.post("/v5/pessoa-fisica/validacao", json=payload, headers=API_HEADERS)
    assert response.status_code == 200
    assert response.json()["cnh"]["documento"]["numero"] is False
    assert response.json()["regra_local"]["validacao_combinada"] is False


def test_generic_attempt_audit_has_no_sensitive_payload(client: TestClient, db: Session):
    seed_identity(db)
    response = client.post(
        "/v1/identity/validate",
        json=identity_payload(),
        headers=API_HEADERS,
    )
    attempt = db.scalar(
        select(ValidationAttempt).where(
            ValidationAttempt.request_id == UUID(response.json()["request_id"])
        )
    )
    assert attempt is not None
    assert attempt.resultado == "aprovado"
    assert attempt.codigo_retorno == "IDENTIDADE_CONFIRMADA"
    assert attempt.person_id is not None
    assert attempt.similaridade_facial is not None
    assert attempt.duracao_ms is not None and attempt.duracao_ms >= 0
    assert attempt.sem_imagem is False
    assert attempt.sem_embedding is False
    evaluated = json.loads(attempt.campos_avaliados or "{}")
    assert evaluated["documento_confirmado"] is True
    assert evaluated["campos"]["numero"] is True
    assert "52998224725" not in (attempt.campos_avaliados or "")
    assert "123456789" not in (attempt.campos_avaliados or "")
    assert synthetic_face() not in (attempt.campos_avaliados or "")
