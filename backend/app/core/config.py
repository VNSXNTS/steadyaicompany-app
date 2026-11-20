"""Configuração lida de variáveis de ambiente. Nenhum segredo fica no código."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_api_key: str
    llm_provider: str
    ollama_url: str
    ollama_model: str
    max_task_attempts: int
    # Orçamento mensal para provedores PAGOS, em dólares. 0 = nenhum gasto autorizado.
    ai_monthly_budget_usd: float
    log_level: str
    frontend_dist: str


def get_settings() -> Settings:
    default_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return Settings(
        # SQLite para desenvolvimento local. Para PostgreSQL:
        # postgresql+psycopg://user:pass@host:5432/steady
        database_url=os.getenv("DATABASE_URL", "sqlite:///./storage/steady.db"),
        # Sem chave configurada, a API protegida recusa todas as chamadas (fail closed).
        admin_api_key=os.getenv("ADMIN_API_KEY", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "mock"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        max_task_attempts=int(os.getenv("MAX_TASK_ATTEMPTS", "3")),
        ai_monthly_budget_usd=float(os.getenv("AI_MONTHLY_BUDGET_USD", "0")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        frontend_dist=os.getenv("FRONTEND_DIST", str(default_dist)),
    )
