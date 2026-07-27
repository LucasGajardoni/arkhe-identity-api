import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _key_bytes(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if len(raw) in {16, 24, 32}:
            return raw
    except Exception:
        pass
    return hashlib.sha256(value.encode("utf-8")).digest()


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    aes = AESGCM(_key_bytes(get_settings().data_encryption_key))
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, value.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    aes = AESGCM(_key_bytes(get_settings().data_encryption_key))
    return aes.decrypt(raw[:12], raw[12:], None).decode("utf-8")


def encrypt_bytes(value: bytes | None) -> str | None:
    if value is None:
        return None
    aes = AESGCM(_key_bytes(get_settings().data_encryption_key))
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, value, None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_bytes(value: str | None) -> bytes | None:
    if value is None:
        return None
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    aes = AESGCM(_key_bytes(get_settings().data_encryption_key))
    return aes.decrypt(raw[:12], raw[12:], None)


def lookup_hmac(value: str) -> str:
    key = _key_bytes(get_settings().lookup_hmac_key)
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_cpf(cpf: str | None) -> str | None:
    if not cpf:
        return None
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if len(digits) != 11:
        return "***"
    return f"{digits[:3]}.***.***-{digits[-2:]}"


def verify_secret(plain: str, configured_hash: str, local_plain: str = "") -> bool:
    if local_plain and hmac.compare_digest(plain, local_plain):
        return True
    if configured_hash:
        try:
            return pwd_context.verify(plain, configured_hash)
        except Exception:
            return hmac.compare_digest(lookup_hmac(plain), configured_hash)
    return False


def create_access_token(subject: str, minutes: int = 120) -> str:
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": datetime.now(UTC) + timedelta(minutes=minutes),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def verify_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        return str(payload.get("sub"))
    except Exception:
        return None
