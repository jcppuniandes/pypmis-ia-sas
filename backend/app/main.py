from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.observability import configure_logging, request_context_middleware
from app.database.seed import seed_demo
from app.database.session import Base, SessionLocal, engine

settings = get_settings()
settings.validate_for_runtime()
configure_logging()

app = FastAPI(
    title=settings.app_name,
    description="API-first Project Controls platform based on AACE TCM.",
    version=settings.app_version,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

if settings.allowed_host_list and "*" not in settings.allowed_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_context_middleware)

app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    if not settings.seed_demo_data:
        return
    db = SessionLocal()
    try:
        seed_demo(db)
    finally:
        db.close()
