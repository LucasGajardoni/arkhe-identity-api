from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_admin
from app.core.config import get_settings
from app.core.exceptions import ArkheError, http_error
from app.core.rate_limit import limiter
from app.core.security import create_access_token, decrypt_text, mask_cpf, verify_secret
from app.db.models import ConsentRecord, FacialReference, ValidationAttempt
from app.repositories.person_repository import PersonRepository
from app.schemas.admin import DocumentCreate, LoginInput, PersonCreate, PersonUpdate, TokenOutput
from app.services.consent import has_active_consent
from app.services.cpf import only_digits
from app.services.facial import FacialService
from app.services.files import decode_base64_image, load_image

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def admin_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/cliente-teste", response_class=HTMLResponse, include_in_schema=False)
def test_client(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("client.html", {"request": request})


@router.post("/auth/login", response_model=TokenOutput)
@limiter.limit(get_settings().admin_login_rate_limit)
def login(payload: LoginInput, request: Request) -> TokenOutput:
    settings = get_settings()
    if payload.username != settings.admin_username or not verify_secret(payload.password, settings.admin_password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas.")
    return TokenOutput(access_token=create_access_token(payload.username))


@router.post("/pessoas", dependencies=[Depends(require_admin)])
def create_person(payload: PersonCreate, db: Session = Depends(db_session)):
    if not payload.consentimento.consentimento_aceito:
        raise http_error("ARKHE_CONSENT_REQUIRED", "Consentimento explicito obrigatorio para cadastro biometrico.")
    repo = PersonRepository(db)
    if repo.find_by_cpf(payload.cpf):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CPF já cadastrado.")
    try:
        person = repo.create_person(payload)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CPF já cadastrado.") from exc
    return {"id": person.id, "cpf_mascarado": mask_cpf(payload.cpf), "nome": person.nome}


@router.get("/pessoas", dependencies=[Depends(require_admin)])
def list_people(db: Session = Depends(db_session)):
    return PersonRepository(db).list_people()


@router.get("/pessoas/{person_id}", dependencies=[Depends(require_admin)])
def get_person(person_id: UUID, db: Session = Depends(db_session)):
    person = PersonRepository(db).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    return {
        "id": person.id,
        "cpf_mascarado": mask_cpf(decrypt_text(person.cpf_encrypted)),
        "nome": person.nome,
        "nome_social": person.nome_social,
        "data_nascimento": person.data_nascimento,
        "sexo": person.sexo,
        "nacionalidade": person.nacionalidade,
        "nome_mae": person.nome_mae,
        "nome_pai": person.nome_pai,
        "situacao_cpf_interna": person.situacao_cpf_interna,
        "status": person.status,
        "consentimento_aceito_em": person.consentimento_aceito_em,
        "documentos": [
            {
                "id": doc.id,
                "tipo": doc.tipo,
                "numero_mascarado": "***" + (decrypt_text(doc.numero_encrypted) or "")[-3:],
                "orgao_expedidor": doc.orgao_expedidor,
                "uf_expedidor": doc.uf_expedidor,
            }
            for doc in person.documents
        ],
    }


@router.patch("/pessoas/{person_id}", dependencies=[Depends(require_admin)])
def update_person(person_id: UUID, payload: PersonUpdate, db: Session = Depends(db_session)):
    repo = PersonRepository(db)
    person = repo.get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    repo.update(person, payload)
    db.commit()
    return {"id": person.id, "status": person.status}


@router.delete("/pessoas/{person_id}", dependencies=[Depends(require_admin)])
def delete_person(person_id: UUID, db: Session = Depends(db_session)):
    repo = PersonRepository(db)
    person = repo.get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    repo.delete_person(person)
    db.commit()
    return {"deleted": True}


@router.post("/pessoas/{person_id}/documentos", dependencies=[Depends(require_admin)])
def add_document(person_id: UUID, payload: DocumentCreate, db: Session = Depends(db_session)):
    repo = PersonRepository(db)
    person = repo.get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    if payload.tipo.value == "CIN":
        person_cpf = only_digits(decrypt_text(person.cpf_encrypted) or "")
        if only_digits(payload.numero) != person_cpf:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O número da CIN deve corresponder ao CPF da pessoa.",
            )
    doc = repo.add_document(person, payload)
    db.commit()
    return {"id": doc.id, "tipo": doc.tipo}


@router.post("/pessoas/{person_id}/referencia-facial", dependencies=[Depends(require_admin)])
async def add_face_reference(
    person_id: UUID,
    imagem: UploadFile | None = File(default=None),
    imagem_base64: str | None = Form(default=None),
    db: Session = Depends(db_session),
):
    repo = PersonRepository(db)
    person = repo.get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    if not has_active_consent(person):
        raise http_error("ARKHE_CONSENT_REQUIRED", "Consentimento valido obrigatorio.")
    try:
        image = load_image(await imagem.read()) if imagem else decode_base64_image(imagem_base64 or "")
        service = FacialService()
        result = service.generate_embedding(image)
        repo.revoke_facial_reference(person)
        db.add(
            FacialReference(
                person_id=person.id,
                embedding_encrypted=service.encrypt_embedding(result.embedding),
                nome_modelo=get_settings().face_model_name,
                versao_modelo=get_settings().face_model_version,
                qualidade_referencia=result.quality,
                imagem_referencia_armazenada=False,
            )
        )
        db.commit()
        return {"registered": True, "quality": result.quality, "stored_image": False}
    except ArkheError as exc:
        raise http_error(exc.code, exc.message) from exc


@router.delete("/pessoas/{person_id}/referencia-facial", dependencies=[Depends(require_admin)])
def revoke_face_reference(person_id: UUID, db: Session = Depends(db_session)):
    repo = PersonRepository(db)
    person = repo.get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    repo.revoke_facial_reference(person)
    db.commit()
    return {"revoked": True}


@router.post("/pessoas/{person_id}/consentimentos", dependencies=[Depends(require_admin)])
def add_consent(person_id: UUID, finalidade: str, versao_termo: str = "arkhe-consent-v1", db: Session = Depends(db_session)):
    person = PersonRepository(db).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    person.consentimento_aceito_em = datetime.now(UTC)
    person.finalidade_consentimento = finalidade
    person.versao_termo_consentimento = versao_termo
    db.add(ConsentRecord(person_id=person.id, finalidade=finalidade, versao_termo=versao_termo))
    db.commit()
    return {"accepted": True}


@router.post("/pessoas/{person_id}/consentimentos/revogar", dependencies=[Depends(require_admin)])
def revoke_consent(person_id: UUID, db: Session = Depends(db_session)):
    person = PersonRepository(db).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa nao encontrada.")
    now = datetime.now(UTC)
    for consent in person.consents:
        if consent.revogado_em is None:
            consent.revogado_em = now
    db.commit()
    return {"revoked": True}


@router.get("/pessoas/{person_id}/exportacao", dependencies=[Depends(require_admin)])
def export_person(person_id: UUID, db: Session = Depends(db_session)):
    data = get_person(person_id, db)
    return JSONResponse(
        content=jsonable_encoder(data),
        headers={"Content-Disposition": "attachment; filename=arkhe-person-export.json"},
    )


@router.get("/auditoria", dependencies=[Depends(require_admin)])
def audit(db: Session = Depends(db_session)):
    attempts = db.scalars(select(ValidationAttempt).order_by(ValidationAttempt.criado_em.desc()).limit(200)).all()
    return [
        {
            "request_id": item.request_id,
            "criado_em": item.criado_em,
            "resultado": item.resultado,
            "codigo_retorno": item.codigo_retorno,
            "similaridade_facial": item.similaridade_facial,
            "sem_imagem": item.sem_imagem,
            "sem_embedding": item.sem_embedding,
        }
        for item in attempts
    ]
