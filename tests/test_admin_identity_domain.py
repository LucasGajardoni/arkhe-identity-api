from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.security import decrypt_text
from app.repositories.person_repository import PersonRepository
from app.schemas.admin import ConsentInput, DocumentCreate, PersonCreate


def person_payload(cpf: str = "529.982.247-25") -> dict:
    return {
        "cpf": cpf,
        "nome": "Pessoa Teste",
        "data_nascimento": "2000-01-01",
        "sexo": "O",
        "nacionalidade": "1",
        "consentimento": {"consentimento_aceito": True},
    }


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/admin/auth/login",
        json={"username": "admin", "password": "admin-test"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_person(db: Session):
    person = PersonRepository(db).create_person(
        PersonCreate(
            cpf="52998224725",
            nome="Pessoa Teste",
            data_nascimento=date(2000, 1, 1),
            sexo="O",
            consentimento=ConsentInput(consentimento_aceito=True),
        )
    )
    db.flush()
    return person


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725"])
def test_person_schema_accepts_valid_formatted_and_plain_cpf(cpf: str):
    assert PersonCreate(**person_payload(cpf)).cpf == "52998224725"


def test_person_schema_rejects_invalid_cpf():
    with pytest.raises(ValidationError, match="CPF inválido"):
        PersonCreate(**person_payload("111.111.111-11"))


def test_admin_rejects_duplicate_cpf_with_conflict(client: TestClient):
    headers = admin_headers(client)
    assert client.post("/admin/pessoas", json=person_payload(), headers=headers).status_code == 200
    response = client.post("/admin/pessoas", json=person_payload("52998224725"), headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "CPF já cadastrado."


def test_unknown_document_type_is_rejected():
    with pytest.raises(ValidationError):
        DocumentCreate(tipo="CARTEIRINHA", numero="123")


def test_document_type_rules():
    rg = DocumentCreate(tipo="RG", numero="123", orgao_expedidor="SSP", uf_expedidor="SP")
    passport = DocumentCreate(tipo="PASSAPORTE", numero="AA123", pais_emissor="BR")
    assert rg.data_validade is None
    assert passport.uf_expedidor is None
    with pytest.raises(ValidationError):
        DocumentCreate(tipo="RG", numero="123")
    with pytest.raises(ValidationError):
        DocumentCreate(tipo="PASSAPORTE", numero="AA123", pais_emissor=None)


def test_cin_must_match_person_cpf(client: TestClient):
    headers = admin_headers(client)
    person = client.post("/admin/pessoas", json=person_payload(), headers=headers).json()
    response = client.post(
        f"/admin/pessoas/{person['id']}/documentos",
        headers=headers,
        json={
            "tipo": "CIN",
            "numero": "12345678900",
            "orgao_expedidor": "SSP",
            "uf_expedidor": "SP",
        },
    )
    assert response.status_code == 422


def test_new_primary_document_demotes_previous(db: Session):
    repo = PersonRepository(db)
    person = create_person(db)
    first = repo.add_document(
        person,
        DocumentCreate(tipo="RG", numero="123", orgao_expedidor="SSP", uf_expedidor="SP"),
    )
    db.flush()
    second = repo.add_document(
        person,
        DocumentCreate(tipo="PASSAPORTE", numero="AA123", pais_emissor="BR"),
    )
    db.flush()
    assert first.principal is False
    assert second.principal is True
    assert decrypt_text(first.numero_encrypted) == "123"
