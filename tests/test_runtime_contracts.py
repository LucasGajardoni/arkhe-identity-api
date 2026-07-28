from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ArkheError
from app.core.rate_limit import limiter
from app.services.facial import FacialService
from tests.conftest import synthetic_face

API_HEADERS = {"X-Arkhe-Api-Key": "test-key"}


def generic_payload() -> dict:
    return {
        "cpf": "52998224725",
        "documento": {
            "tipo": "RG",
            "numero": "123456789",
            "orgao_expedidor": "SSP",
            "uf_expedidor": "SP",
        },
        "selfie": {"imagem_base64": synthetic_face()},
    }


def v5_payload() -> dict:
    return {
        "cpf": "52998224725",
        "validacao": {
            "nome": "Pessoa Teste",
            "data_nascimento": "2000-01-01",
            "documento": {
                "tipo": 1,
                "numero": "123456789",
                "orgao_expedidor": "SSP",
                "uf_expedidor": "SP",
            },
        },
        "biometria_facial": {"imagem": synthetic_face(), "vivacidade": False},
    }


def test_invalid_admin_login(client: TestClient):
    response = client.post(
        "/admin/auth/login",
        json={"username": "admin", "password": "incorrect"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("headers", [{}, {"X-Arkhe-Api-Key": "invalid"}])
def test_generic_api_rejects_missing_or_invalid_api_key(
    client: TestClient,
    headers: dict[str, str],
):
    response = client.post("/v1/identity/validate", json=generic_payload(), headers=headers)
    assert response.status_code == 401


def test_inactive_person_is_rejected(client: TestClient, db):
    from tests.test_identity_api import seed_identity

    seed_identity(db, status="bloqueado")
    response = client.post(
        "/v1/identity/validate",
        json=generic_payload(),
        headers=API_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["codigo"] == "PESSOA_INATIVA"


@pytest.mark.parametrize(
    ("error_code", "expected_code"),
    [
        ("ARKHE_NO_FACE", "ARKHE_NO_FACE"),
        ("ARKHE_MULTIPLE_FACES", "ARKHE_MULTIPLE_FACES"),
        ("ARKHE_UNSUPPORTED_IMAGE", "ARKHE_UNSUPPORTED_IMAGE"),
    ],
)
def test_v5_preserves_historical_facial_errors(
    client: TestClient,
    db,
    monkeypatch,
    error_code: str,
    expected_code: str,
):
    from tests.test_identity_api import seed_identity

    seed_identity(db)

    def raise_facial_error(*_args, **_kwargs):
        raise ArkheError(error_code, "Erro facial de teste.")

    if error_code == "ARKHE_UNSUPPORTED_IMAGE":
        payload = deepcopy(v5_payload())
        payload["biometria_facial"]["imagem"] = "invalid-base64"
    else:
        monkeypatch.setattr(FacialService, "generate_embedding", raise_facial_error)
        payload = v5_payload()
    response = client.post(
        "/v5/pessoa-fisica/validacao",
        json=payload,
        headers=API_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["codigo"] == expected_code


@pytest.mark.parametrize(
    ("path", "payload", "headers", "allowed_requests"),
    [
        (
            "/admin/auth/login",
            {"username": "admin", "password": "incorrect"},
            {},
            20,
        ),
        ("/v1/identity/validate", generic_payload(), API_HEADERS, 120),
        ("/v5/pessoa-fisica/validacao", v5_payload(), API_HEADERS, 120),
    ],
)
def test_rate_limits_are_enforced(
    client: TestClient,
    path: str,
    payload: dict,
    headers: dict[str, str],
    allowed_requests: int,
):
    limiter.reset()
    responses = [
        client.post(path, json=payload, headers=headers)
        for _ in range(allowed_requests + 1)
    ]
    assert responses[-1].status_code == 429
