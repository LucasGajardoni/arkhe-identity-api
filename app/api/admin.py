from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_admin
from app.core.config import get_settings
from app.core.security import create_access_token, verify_secret
from app.db.models import AuditEvent, ClientApplication, Identity
from app.repositories.identity_repository import IdentityRepository
from app.schemas.identity import (
    ClientApplicationCreate,
    ClientApplicationCreated,
    LoginInput,
    TokenOutput,
)
from app.services.sessions import hash_client_secret

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/scanner", response_class=HTMLResponse, name="scanner_page")
def scanner_page(request: Request):
    return templates.TemplateResponse("scanner.html", {"request": request})


@router.post("/auth/login", response_model=TokenOutput)
def login(payload: LoginInput, response: Response):
    settings = get_settings()
    if payload.username != settings.admin_username or not verify_secret(payload.password, settings.admin_password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas.")
    token = create_access_token(payload.username)
    response.set_cookie(
        "arkhe_admin_token",
        token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=7200,
    )
    return TokenOutput(access_token=token)


@router.post("/client-applications", response_model=ClientApplicationCreated, status_code=201)
def create_client_application(
    payload: ClientApplicationCreate,
    _: str = Depends(require_admin),
    db: Session = Depends(db_session),
):
    if IdentityRepository(db).client_by_slug(payload.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug ja cadastrado.")
    client = IdentityRepository(db).create_client(
        name=payload.name,
        slug=payload.slug,
        secret_hash=hash_client_secret(payload.client_secret),
        allowed_origins="\n".join(payload.allowed_origins),
    )
    db.commit()
    return ClientApplicationCreated(id=client.id, name=client.name, slug=client.slug)


@router.get("/client-applications")
def list_client_applications(_: str = Depends(require_admin), db: Session = Depends(db_session)):
    clients = db.scalars(select(ClientApplication).order_by(ClientApplication.created_at.desc()).limit(200)).all()
    return [
        {
            "id": client.id,
            "name": client.name,
            "slug": client.slug,
            "is_active": client.is_active,
            "created_at": client.created_at,
        }
        for client in clients
    ]


@router.get("/identities")
def list_identities(_: str = Depends(require_admin), db: Session = Depends(db_session)):
    identities = db.scalars(select(Identity).order_by(Identity.created_at.desc()).limit(200)).all()
    return [IdentityRepository.public_identity(identity) for identity in identities]


@router.delete("/identities/{identity_id}/biometric-template")
def reset_identity_biometric(
    identity_id: str,
    _: str = Depends(require_admin),
    db: Session = Depends(db_session),
):
    try:
        from uuid import UUID
        identity_uuid = UUID(identity_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Identidade invalida.")

    repo = IdentityRepository(db)
    identity = repo.get_identity(identity_uuid)

    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identidade nao encontrada.")

    quantidade = repo.revoke_active_templates(identity)

    if quantidade == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta identidade ja esta sem biometria ativa.")

    db.add(AuditEvent(
        client_application_id=identity.client_application_id,
        identity_id=identity.id,
        event_type="biometric.reset",
        outcome="ok",
    ))
    db.commit()

    return {
        "mensagem": "Biometria resetada. No proximo acesso sera necessario cadastrar o rosto novamente.",
        "identity_id": identity.id,
        "templates_revogados": quantidade,
    }


@router.get("/audit-events")
def list_audit_events(_: str = Depends(require_admin), db: Session = Depends(db_session)):
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)).all()
    return [
        {
            "id": event.id,
            "client_application_id": event.client_application_id,
            "identity_id": event.identity_id,
            "event_type": event.event_type,
            "outcome": event.outcome,
            "created_at": event.created_at,
        }
        for event in events
    ]
