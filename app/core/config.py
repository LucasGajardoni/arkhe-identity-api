from functools import lru_cache

from pydantic import Field
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
