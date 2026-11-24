import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.routes import router
from app.core.config import Settings, get_settings, validate_production_settings
from app.core.logging import setup_logging
from app.database.session import Base, SessionLocal, engine
from app.models import entities  # noqa: F401  (registra os modelos)
from app.services.agent_registry import seed_agents
from app.services.auth import ensure_owner_account

setup_logging(get_settings().log_level)
logger = logging.getLogger("steady.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Para produção, troque create_all por migrações Alembic (ainda não incluídas).
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_agents(db, model_name=get_settings().llm_provider)
        ensure_owner_account(db)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Monta o app. Em produção recusa configuração insegura e desliga /docs, /redoc e /openapi.json."""
    settings = settings or get_settings()
    validate_production_settings(settings)  # levanta RuntimeError com mensagem clara
    docs = {} if not settings.is_production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    application = FastAPI(title="Steady AI Company", version="0.2.0", lifespan=lifespan, **docs)

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        """Registra método, caminho, status e duração. Não registra cabeçalhos nem corpo (há chaves neles)."""
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("erro não tratado", extra={"request_id": request_id, "method": request.method,
                                                       "path": request.url.path})
            return JSONResponse({"detail": "Erro interno", "request_id": request_id}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        logger.info("request", extra={"request_id": request_id, "method": request.method,
                                      "path": request.url.path, "status": response.status_code,
                                      "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    application.include_router(router)
    application.include_router(auth_router)

    @application.get("/health")
    def health():
        """Público e barato: só confere o banco. Use /providers/status (autenticado) para o provedor de IA."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable",
                "llm_provider": get_settings().llm_provider, "version": application.version}

    # Serve o painel (frontend/dist) quando ele foi compilado. As rotas da API têm prioridade.
    if os.path.isdir(settings.frontend_dist):
        application.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return application


app = create_app()
