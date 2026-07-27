from typing import Protocol

from app.schemas.datavalid import DatavalidCompatibleV5Request, DatavalidCompatibleV5Response


class IdentityValidationProvider(Protocol):
    def validate_identity(self, request: DatavalidCompatibleV5Request) -> DatavalidCompatibleV5Response:
        ...
