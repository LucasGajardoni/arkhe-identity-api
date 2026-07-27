from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.validation import DatavalidProvider, PrivateRegistryProvider


def get_identity_provider(db: Session):
    provider = get_settings().identity_provider
    if provider == "datavalid":
        return DatavalidProvider()
    return PrivateRegistryProvider(db)
