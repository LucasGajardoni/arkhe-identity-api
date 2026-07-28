from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Arkhe Identity API"
    environment: str = "local"
    port: int = 8000
    debug: bool = False
    database_url: str = "postgresql+psycopg://arkhe:arkhe_dev_password@localhost:5432/arkhe_identity"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    data_encryption_key: str = Field(default="development-only-32-byte-key!!")
    lookup_hmac_key: str = Field(default="development-only-hmac-key-change")
    jwt_secret: str = "development-only-jwt-secret"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    api_key_hash: str = ""
    api_key_plaintext_for_local_only: str = "local-dev-api-key"

    require_privacy_object: bool = False
    text_similarity_threshold: float = 0.90
    facial_similarity_threshold: float = 0.85
    facial_threshold_experimental: bool = True
    max_image_size_mb: int = 3
    store_reference_images: bool = False
    reference_image_dir: str = "/tmp/arkhe-reference-images"
    identity_provider: str = "private_registry"
    face_model_name: str = "opencv-yunet-sface"
    face_model_version: str = "YuNet-2023mar-SFace-2021dec"
    face_backend: str = "opencv"
    face_detector_model_path: str = "models/face_detection_yunet_2023mar.onnx"
    face_recognizer_model_path: str = "models/face_recognition_sface_2021dec.onnx"
    enable_api_docs: bool = True
    admin_login_rate_limit: str = "20/minute"
    identity_validation_rate_limit: str = "120/minute"
    v5_validation_rate_limit: str = "120/minute"

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.environment.lower() not in {"production", "prod"}:
            return self
        insecure_markers = ("development-only", "change-me", "replace", "gerar_com", "local-dev")
        secrets = {
            "DATA_ENCRYPTION_KEY": self.data_encryption_key,
            "LOOKUP_HMAC_KEY": self.lookup_hmac_key,
            "JWT_SECRET": self.jwt_secret,
            "ADMIN_PASSWORD_HASH": self.admin_password_hash,
            "API_KEY_HASH": self.api_key_hash,
        }
        invalid = [
            name
            for name, value in secrets.items()
            if not value or any(marker in value.lower() for marker in insecure_markers)
        ]
        if self.api_key_plaintext_for_local_only:
            invalid.append("API_KEY_PLAINTEXT_FOR_LOCAL_ONLY")
        if self.face_backend.lower() == "fake":
            invalid.append("FACE_BACKEND")
        if "*" in self.cors_origin_list:
            invalid.append("CORS_ORIGINS")
        database_url = self.database_url.lower()
        if not database_url.startswith("postgresql+psycopg://") or "@localhost" in database_url:
            invalid.append("DATABASE_URL")
        if invalid:
            raise ValueError(
                "Configuração insegura para produção: " + ", ".join(sorted(set(invalid)))
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
