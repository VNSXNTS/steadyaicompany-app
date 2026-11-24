"""Configuração lida de variáveis de ambiente. Nenhum segredo fica no código."""
import ipaddress
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
    log_level: str
    frontend_dist: str
    # "production" liga as travas de segurança (cookie Secure obrigatório, /docs desligado).
    app_env: str = "development"
    # Proxies reversos em que confiamos para ler X-Forwarded-For (IPs ou CIDRs). Vazio = ninguém.
    trusted_proxies: tuple[str, ...] = ()
    # Origens extras aceitas em requisições que alteram dados (além do próprio Host).
    allowed_origins: tuple[str, ...] = ()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _csv(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


def _parse_trusted_proxies() -> tuple[str, ...]:
    items = _csv("TRUSTED_PROXIES")
    for item in items:
        try:
            ipaddress.ip_network(item, strict=False)
        except ValueError as exc:
            raise ValueError(f"TRUSTED_PROXIES contém um valor inválido: {item!r} (use IPs ou CIDRs)") from exc
    return items


def validate_production_settings(settings: Settings) -> None:
    """Impede a inicialização em produção com configuração insegura."""
    if settings.app_env not in ("development", "test", "production"):
        raise RuntimeError(
            f"APP_ENV={settings.app_env!r} não é reconhecido. Use development, test ou production."
        )
    if settings.is_production and not settings.auth_cookie_secure:
        raise RuntimeError(
            "Configuração insegura: APP_ENV=production exige AUTH_COOKIE_SECURE=true "
            "(o cookie de sessão só pode trafegar por HTTPS). Sirva o painel por HTTPS e defina "
            "AUTH_COOKIE_SECURE=true, ou use APP_ENV=development para testes locais em HTTP."
        )


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
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        frontend_dist=os.getenv("FRONTEND_DIST", str(default_dist)),
        app_env=os.getenv("APP_ENV", "development").strip().lower(),
        trusted_proxies=_parse_trusted_proxies(),
        allowed_origins=tuple(o.rstrip("/") for o in _csv("ALLOWED_ORIGINS")),
    )
