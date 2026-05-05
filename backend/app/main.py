import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.observability import request_context_middleware
from app.database.seed import seed_demo
from app.database.session import Base, SessionLocal, engine


settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

app = FastAPI(
    title=settings.app_name,
    description="API-first Project Controls platform based on AACE TCM.",
    version="0.1.0",
)

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
