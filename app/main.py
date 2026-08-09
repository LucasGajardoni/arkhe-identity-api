from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import admin, health, identity
from app.core.config import get_settings
from app.core.exceptions import ArkheError
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Arkhe Identity API",
    description="Plataforma multi-tenant para cadastro e verificacao facial via API.",
    version="0.1.0",
)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Client-Id", "X-Client-Secret"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(health.router)
app.include_router(identity.router)
app.include_router(admin.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self)"
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Limite de requisicoes excedido."})


@app.exception_handler(ArkheError)
async def arkhe_error_handler(request: Request, exc: ArkheError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": {"code": exc.code, "message": exc.message}})
