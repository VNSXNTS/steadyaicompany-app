"""Configuração lida de variáveis de ambiente. Nenhum segredo fica no código."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_api_key: str
    owner_email: str
    owner_password: str
    auth_cookie_secure: bool
    llm_provider: str
    ollama_url: str
    ollama_model: str
    max_task_attempts: int
    # Orçamento mensal para provedores PAGOS, em dólares. 0 = nenhum gasto autorizado.
    ai_monthly_budget_usd: float
    # Provedores pagos (Fase 9). Sem chave, modelo e preços informados, o provedor fica bloqueado.
    anthropic_api_key: str
    anthropic_model: str
    anthropic_base_url: str
    anthropic_input_usd_per_mtok: float
    anthropic_output_usd_per_mtok: float
    gemini_api_key: str
    gemini_model: str
    gemini_base_url: str
    gemini_input_usd_per_mtok: float
    gemini_output_usd_per_mtok: float
    ai_max_output_tokens: int  # teto de saída por chamada: limita o pior caso de custo
    llm_fallback_provider: str  # "" ou "ollama": usado só quando um provedor pago está bloqueado
    log_level: str
    frontend_dist: str


def _num(name: str, default: str, cast=float):
    """Lê número de variável de ambiente; vazio (como no .env.example) vale o padrão. Valor inválido falha alto."""
    raw = os.getenv(name, "").strip() or default
    try:
        return cast(raw)
    except ValueError:
        raise RuntimeError(f"{name} inválida: {raw!r} (esperado número)") from None


def get_settings() -> Settings:
    default_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return Settings(
        # SQLite para desenvolvimento local. Para PostgreSQL:
        # postgresql+psycopg://user:pass@host:5432/steady
        database_url=os.getenv("DATABASE_URL", "sqlite:///./storage/steady.db"),
        # Sem chave configurada, a API protegida recusa todas as chamadas (fail closed).
        admin_api_key=os.getenv("ADMIN_API_KEY", ""),
        owner_email=os.getenv("OWNER_EMAIL", "").strip().lower(),
        owner_password=os.getenv("OWNER_PASSWORD", ""),
        auth_cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() in ("1", "true", "yes"),
        llm_provider=os.getenv("LLM_PROVIDER", "mock"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        max_task_attempts=int(os.getenv("MAX_TASK_ATTEMPTS", "3")),
        ai_monthly_budget_usd=float(os.getenv("AI_MONTHLY_BUDGET_USD", "0")),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "").strip(),
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/"),
        anthropic_input_usd_per_mtok=_num("ANTHROPIC_INPUT_USD_PER_MTOK", "0"),
        anthropic_output_usd_per_mtok=_num("ANTHROPIC_OUTPUT_USD_PER_MTOK", "0"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "").strip(),
        gemini_base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/"),
        gemini_input_usd_per_mtok=_num("GEMINI_INPUT_USD_PER_MTOK", "0"),
        gemini_output_usd_per_mtok=_num("GEMINI_OUTPUT_USD_PER_MTOK", "0"),
        ai_max_output_tokens=_num("AI_MAX_OUTPUT_TOKENS", "1024", int),
        llm_fallback_provider=os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower(),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        frontend_dist=os.getenv("FRONTEND_DIST", str(default_dist)),
    )
