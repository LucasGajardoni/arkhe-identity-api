from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ConsentRecord, FacialReference
from app.repositories.person_repository import PersonRepository
from app.schemas.admin import ConsentInput, DocumentCreate, PersonCreate
from app.services.facial import FacialService
from app.services.files import decode_base64_image
from tests.conftest import synthetic_face


def create_person(db: Session, *, status="ativo", consent=True, with_face=True):
    repo = PersonRepository(db)
    person = repo.create_person(
        PersonCreate(
            cpf="52998224725",
            nome="Joao Arkhe",
            data_nascimento=date(2000, 1, 1),
            sexo="M",
            nacionalidade="1",
            nome_mae="Maria Arkhe",
            nome_pai="Jose Arkhe",
            situacao_cpf_interna="regular",
            consentimento=ConsentInput(consentimento_aceito=consent),
            status=status,
        )
    )
    repo.add_document(person, DocumentCreate(tipo="RG", numero="123456789", orgao_expedidor="SSP", uf_expedidor="SP"))
    if with_face:
        svc = FacialService()
        emb = svc.generate_embedding(decode_base64_image(synthetic_face())).embedding
        db.add(
            FacialReference(
                person_id=person.id,
                embedding_encrypted=svc.encrypt_embedding(emb),
                nome_modelo="fake",
                versao_modelo="test",
                qualidade_referencia=0.9,
                imagem_referencia_armazenada=False,
            )
        )
    db.commit()
    return person


def payload(**overrides):
    base = {
        "cpf": "52998224725",
        "validacao": {
            "nome": "Joao Arkhe",
            "data_nascimento": "2000-01-01",
            "sexo": "M",
            "nacionalidade": 1,
            "nome_mae": "Maria Arkhe",
            "nome_pai": "Jose Arkhe",
            "rfb": {"situacao_cpf": "regular"},
            "documento": {"tipo": 1, "numero": "123456789", "orgao_expedidor": "SSP", "uf_expedidor": "SP"},
        },
        "biometria_facial": {"imagem": synthetic_face(), "vivacidade": False},
    }
    base.update(overrides)
    return base


def test_cpf_not_found(client: TestClient):
    res = client.post("/v5/pessoa-fisica/validacao", json=payload(), headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.status_code == 200
    assert res.json()["rfb_existe"] is False


def test_exact_name_and_document_and_birth(client: TestClient, db: Session):
    create_person(db)
    res = client.post("/v5/pessoa-fisica/validacao", json=payload(), headers={"X-Arkhe-Api-Key": "test-key"})
    data = res.json()
    assert data["rfb"]["nome"] is True
    assert data["rfb"]["data_nascimento"] is True
    assert data["cnh"]["documento"]["numero"] is True
    assert "embedding" not in res.text
    assert "data:image" not in res.text


def test_name_accents_and_case_similarity(client: TestClient, db: Session):
    create_person(db)
    changed = payload()
    changed["validacao"]["nome"] = "joao arkhe"
    res = client.post("/v5/pessoa-fisica/validacao", json=changed, headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.json()["rfb"]["nome_similaridade"] == 1.0


def test_really_divergent_name(client: TestClient, db: Session):
    create_person(db)
    changed = payload()
    changed["validacao"]["nome"] = "Pessoa Totalmente Diferente"
    res = client.post("/v5/pessoa-fisica/validacao", json=changed, headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.json()["rfb"]["nome"] is False


def test_wrong_birth_and_document(client: TestClient, db: Session):
    create_person(db)
    changed = payload()
    changed["validacao"]["data_nascimento"] = "1999-01-01"
    changed["validacao"]["documento"]["numero"] = "999"
    res = client.post("/v5/pessoa-fisica/validacao", json=changed, headers={"X-Arkhe-Api-Key": "test-key"})
    data = res.json()
    assert data["rfb"]["data_nascimento"] is False
    assert data["cnh"]["documento"]["numero"] is False


def test_person_without_face_reference(client: TestClient, db: Session):
    create_person(db, with_face=False)
    res = client.post("/v5/pessoa-fisica/validacao", json=payload(), headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.json()["biometria_facial"]["codigo_retorno"] == "ARKHE_FACE_NOT_REGISTERED"


def test_invalid_image(client: TestClient, db: Session):
    create_person(db)
    changed = payload(biometria_facial={"imagem": "not-base64", "vivacidade": False})
    res = client.post("/v5/pessoa-fisica/validacao", json=changed, headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.status_code == 422
    assert res.json()["detail"]["codigo"] == "ARKHE_UNSUPPORTED_IMAGE"


def test_genuine_and_divergent_face(client: TestClient, db: Session):
    create_person(db)
    good = client.post("/v5/pessoa-fisica/validacao", json=payload(), headers={"X-Arkhe-Api-Key": "test-key"}).json()
    bad_payload = payload(biometria_facial={"imagem": synthetic_face((20, 40, 80)), "vivacidade": False})
    bad = client.post("/v5/pessoa-fisica/validacao", json=bad_payload, headers={"X-Arkhe-Api-Key": "test-key"}).json()
    assert good["biometria_facial"]["similaridade"] >= bad["biometria_facial"]["similaridade"]


def test_consent_revoked_and_blocked(client: TestClient, db: Session):
    person = create_person(db, status="bloqueado")
    db.add(ConsentRecord(person_id=person.id, finalidade="x", versao_termo="v1", revogado_em=datetime(2026, 1, 1, tzinfo=UTC)))
    db.commit()
    res = client.post("/v5/pessoa-fisica/validacao", json=payload(), headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.status_code == 200
    assert res.json()["regra_local"]["validacao_combinada"] is False


def test_liveness_true_rejected(client: TestClient, db: Session):
    create_person(db)
    changed = payload(biometria_facial={"imagem": synthetic_face(), "vivacidade": True})
    res = client.post("/v5/pessoa-fisica/validacao", json=changed, headers={"X-Arkhe-Api-Key": "test-key"})
    assert res.status_code == 422
    assert res.json()["detail"]["codigo"] == "ARKHE_LIVENESS_NOT_SUPPORTED"


def test_complete_person_deletion(client: TestClient, db: Session):
    person = create_person(db)
    token = client.post("/admin/auth/login", json={"username": "admin", "password": "admin-test"}).json()["access_token"]
    res = client.delete(f"/admin/pessoas/{person.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert PersonRepository(db).get(person.id) is None
