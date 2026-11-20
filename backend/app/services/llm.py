"""Camada de abstração de provedores de IA. Trocar o modelo não exige reescrever o sistema.

Implementados: MockProvider (testes e desenvolvimento sem custo) e OllamaProvider (modelo local).
Claude e Gemini podem ser adicionados implementando a mesma interface; ainda NÃO existem aqui.

Regras de custo:
- Provedores com `paid = True` só rodam se houver orçamento mensal autorizado (AI_MONTHLY_BUDGET_USD > 0).
- Todo uso é registrado na tabela ai_usage (tokens e custo), inclusive chamadas que falharam.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""
    paid: bool = False  # True: consome dinheiro e exige orçamento autorizado

    @abstractmethod
    def complete(self, system: str, prompt: str) -> LLMResult:
        ...

    def cost_micro_usd(self, prompt_tokens: int, completion_tokens: int) -> int:
        """Custo estimado em milionésimos de dólar. Provedores gratuitos retornam 0."""
        return 0

    def check(self) -> tuple[bool, str]:
        """Verifica se o provedor está utilizável agora. Não consome tokens."""
        return True, "sem verificação implementada"


class MockProvider(LLMProvider):
    """Não chama nenhum modelo. A saída é marcada para ninguém confundir com trabalho real."""

    name = "mock"
    model = "mock"

    def complete(self, system: str, prompt: str) -> LLMResult:
        return LLMResult(text=f"[MOCK: nenhum modelo de IA foi chamado] Tarefa recebida: {prompt[:200]}")

    def check(self) -> tuple[bool, str]:
        return True, "modo simulado: nenhum modelo real em uso"


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, url: str, model: str, timeout: float = 120.0):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, prompt: str) -> LLMResult:
        resp = httpx.post(
            f"{self.url}/api/generate",
            json={"model": self.model, "system": system, "prompt": prompt, "stream": False},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResult(
            text=data.get("response", ""),
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
        )

    def check(self) -> tuple[bool, str]:
        try:
            resp = httpx.get(f"{self.url}/api/tags", timeout=3.0)
            resp.raise_for_status()
            names = [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception as exc:
            return False, f"Ollama inacessível em {self.url}: {type(exc).__name__}"
        wanted = self.model.split(":")[0]
        if not any(n.split(":")[0] == wanted for n in names):
            return False, f"Ollama responde, mas o modelo '{self.model}' não está instalado"
        return True, f"Ollama ok com o modelo '{self.model}'"


def get_provider() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "ollama":
        return OllamaProvider(s.ollama_url, s.ollama_model)
    if s.llm_provider == "mock":
        return MockProvider()
    raise ValueError(f"LLM_PROVIDER desconhecido: {s.llm_provider!r} (use 'mock' ou 'ollama')")
