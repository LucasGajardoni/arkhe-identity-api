from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_api_key
from app.core.config import get_settings
from app.core.exceptions import ArkheError, http_error
from app.core.rate_limit import limiter
from app.providers import get_identity_provider
from app.schemas.datavalid import DatavalidCompatibleV5Request, DatavalidCompatibleV5Response

router = APIRouter(prefix="/v5/pessoa-fisica", tags=["validacao"])


@router.post("/validacao", response_model=DatavalidCompatibleV5Response)
@limiter.limit(get_settings().v5_validation_rate_limit)
def validate_person(
    payload: DatavalidCompatibleV5Request,
    request: Request,
    _: None = Depends(require_api_key),
    db: Session = Depends(db_session),
) -> DatavalidCompatibleV5Response:
    try:
        response = get_identity_provider(db).validate_identity(payload)
        db.commit()
        return response
    except ArkheError as exc:
        db.rollback()
        if exc.code in {"ARKHE_LIVENESS_NOT_SUPPORTED", "ARKHE_INVALID_REQUEST", "ARKHE_UNSUPPORTED_IMAGE"}:
            raise http_error(exc.code, exc.message, status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
        raise http_error(exc.code, exc.message) from exc
