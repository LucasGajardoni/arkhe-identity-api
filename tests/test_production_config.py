import pytest
from pydantic import ValidationError

from app.core.config import Settings


def valid_production_settings() -> dict[str, str]:
    return {
        "environment": "production",
        "database_url": (
            "postgresql+psycopg://fixture_user:fixture_password"
            "@postgres.internal:5432/fixture_database"
        ),
        "data_encryption_key": "fixture-encryption-material-with-sufficient-entropy",
        "lookup_hmac_key": "fixture-hmac-material-with-sufficient-entropy",
        "jwt_secret": "".join(("fixture-jwt-material-", "with-sufficient-entropy")),
        "admin_password_hash": "".join(("$2b$12$", "fixturehashmaterial")),
        "api_key_hash": "".join(("$2b$12$", "fixtureapikeyhashmaterial")),
        "api_key_plaintext_for_local_only": "",
        "face_backend": "opencv",
        "cors_origins": "https://identity.example.test",
    }


def test_production_rejects_development_secrets():
    insecure_jwt_placeholder = "-".join(("change", "me"))
    with pytest.raises(ValidationError, match="Configuração insegura"):
        Settings(
            environment="production",
            data_encryption_key="development-only-32-byte-key!!",
            lookup_hmac_key="development-only-hmac-key-change",
            jwt_secret=insecure_jwt_placeholder,
            admin_password_hash="",
            api_key_hash="",
            api_key_plaintext_for_local_only="local-dev-api-key",
        )


def test_local_environment_keeps_development_compatibility():
    assert Settings(environment="test").environment == "test"


def test_production_accepts_non_placeholder_secrets():
    settings = Settings(**valid_production_settings())
    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("data_encryption_key", "-".join(("development", "only"))),
        ("lookup_hmac_key", "-".join(("development", "only"))),
        ("jwt_secret", "-".join(("change", "me"))),
        ("admin_password_hash", "".join(("re", "place"))),
        ("api_key_hash", "_".join(("GERAR", "COM"))),
        ("api_key_hash", ""),
        ("api_key_plaintext_for_local_only", "-".join(("local", "dev", "key"))),
    ],
)
def test_each_insecure_production_marker_is_rejected(field: str, value: str):
    values = valid_production_settings()
    values[field] = value
    with pytest.raises(ValidationError, match="Configuração insegura"):
        Settings(**values)


def test_production_rejects_fake_face_backend():
    values = valid_production_settings()
    values["face_backend"] = "fake"
    with pytest.raises(ValidationError, match="FACE_BACKEND"):
        Settings(**values)


def test_production_rejects_wildcard_cors_with_credentials():
    values = valid_production_settings()
    values["cors_origins"] = "*"
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**values)


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+pysqlite:///local.db",
        "postgresql+psycopg://fixture:fixture@localhost:5432/fixture",
    ],
)
def test_production_rejects_non_remote_postgresql(database_url: str):
    values = valid_production_settings()
    values["database_url"] = database_url
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(**values)
