from fastapi import HTTPException, status


class ArkheError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def http_error(code: str, message: str, http_status: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"codigo": code, "mensagem": message})
