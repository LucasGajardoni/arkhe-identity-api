import hashlib
import time
from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import verify_access_token, verify_secret
from app.db.models import ClientApplication
from app.db.session import get_db
from app.repositories.identity_repository import IdentityRepository

_RATE_WINDOW_SECONDS = 60
_RATE_MAX_REQUESTS = 10
_rate_buckets: dict[str, list[float]] = {}


def db_session() -> Generator[Session, None, None]:
    yield from get_db()


def require_client_application(
    db: Session = Depends(db_session),
    x_client_id: str = Header(default="", alias="X-Client-Id"),
    x_client_secret: str = Header(default="", alias="X-Client-Secret"),
) -> ClientApplication:
    client = IdentityRepository(db).client_by_slug(x_client_id)
    if client is None or not verify_secret(x_client_secret, client.secret_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais da aplicacao cliente invalidas.")
    return client


def require_admin(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else request.cookies.get("arkhe_admin_token", "")
    subject = verify_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao administrativa obrigatoria.")
    return subject


def rate_limit(request: Request) -> None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)

    authorization = request.headers.get("authorization", "")
    client_id = request.headers.get("x-client-id", "")

    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        identificador = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    elif client_id:
        identificador = client_id
    else:
        identificador = request.client.host if request.client else "unknown"

    limite = 120 if route_path.endswith("/attempts") or route_path.endswith("/captures") else 60
    key = f"{identificador}:{route_path}"
    now = time.monotonic()

    bucket = [item for item in _rate_buckets.get(key, []) if now - item < _RATE_WINDOW_SECONDS]

    if len(bucket) >= limite:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Limite de requisicoes excedido.")

    bucket.append(now)
    _rate_buckets[key] = bucket
