from collections.abc import Generator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_access_token, verify_secret
from app.db.session import get_db


def db_session() -> Generator[Session, None, None]:
    yield from get_db()


def require_api_key(x_arkhe_api_key: str = Header(default="")) -> None:
    settings = get_settings()
    if not verify_secret(x_arkhe_api_key, settings.api_key_hash, settings.api_key_plaintext_for_local_only):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key invalida.")


def require_admin(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else request.cookies.get("arkhe_admin_token", "")
    subject = verify_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao administrativa obrigatoria.")
    return subject
