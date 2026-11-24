"""Camada de abstração de provedores de IA. Trocar o modelo não exige reescrever o sistema.

Implementados: MockProvider (testes e desenvolvimento sem custo), OllamaProvider (modelo local) e, pagos,
ClaudeProvider e GeminiProvider (Fase 9). Os pagos só rodam com chave, modelo E preços por milhão de tokens
informados por variável de ambiente (preços mudam; o sistema não assume nenhum) e dentro do orçamento mensal.

Regras de custo:
- Provedores com `paid = True` só rodam se houver orçamento mensal autorizado (AI_MONTHLY_BUDGET_USD > 0).
- Todo uso é registrado na tabela ai_usage (tokens e custo), inclusive chamadas que falharam.
"""
import math
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

    def blocked_reason(self) -> str | None:
        """Motivo pelo qual o provedor não pode rodar agora (configuração faltando), ou None."""
        return None

    def estimate_max_cost_micro_usd(self, prompt: str) -> int:
        """Pior caso de uma chamada, usado ANTES de gastar. Gratuitos: 0."""
        return 0


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


class _PaidHTTPProvider(LLMProvider):
    """Base dos provedores pagos: configuração obrigatória, custo por preço informado, nunca expõe a chave."""

    paid = True
    label = ""

    def __init__(self, api_key: str, model: str, base_url: str, in_price: float, out_price: float,
                 max_output_tokens: int, timeout: float = 120.0):
        self._key = api_key
        self.model = model
        self.base_url = base_url
        self.in_price, self.out_price = in_price, out_price  # US$ por milhão de tokens == micro-US$ por token
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout

    def blocked_reason(self) -> str | None:
        missing = []
        if not self._key:
            missing.append("chave de API")
        if not self.model:
            missing.append("modelo")
        if self.in_price <= 0 or self.out_price <= 0:
            missing.append("preços por milhão de tokens (entrada e saída)")
        if missing:
            return f"{self.label} bloqueado: faltam " + ", ".join(missing) + " na configuração"
        return None

    def cost_micro_usd(self, prompt_tokens: int, completion_tokens: int) -> int:
        return math.ceil(prompt_tokens * self.in_price + completion_tokens * self.out_price)

    def estimate_max_cost_micro_usd(self, prompt: str) -> int:
        est_prompt_tokens = len(prompt) // 3 + 1  # estimativa conservadora (menos de 3 caracteres por token)
        return self.cost_micro_usd(est_prompt_tokens, self.max_output_tokens)

    def check(self) -> tuple[bool, str]:
        reason = self.blocked_reason()
        if reason:
            return False, reason
        return True, (f"{self.label} configurado com o modelo '{self.model}'. NÃO testado contra o serviço: "
                      "testar consome tokens e dinheiro")

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        reason = self.blocked_reason()
        if reason:
            raise RuntimeError(reason)
        resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:  # sem o corpo da resposta: nada vaza para logs e tarefas
            raise RuntimeError(f"{self.label} respondeu HTTP {resp.status_code}")
        return resp.json()


class ClaudeProvider(_PaidHTTPProvider):
    name = "claude"
    label = "Claude"

    def complete(self, system: str, prompt: str) -> LLMResult:
        data = self._post(
            f"{self.base_url}/v1/messages",
            {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": self.model, "max_tokens": self.max_output_tokens, "system": system,
             "messages": [{"role": "user", "content": prompt}]})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResult(text=text, prompt_tokens=int(usage.get("input_tokens") or 0),
                         completion_tokens=int(usage.get("output_tokens") or 0))


class GeminiProvider(_PaidHTTPProvider):
    name = "gemini"
    label = "Gemini"

    def complete(self, system: str, prompt: str) -> LLMResult:
        data = self._post(
            f"{self.base_url}/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": self._key, "content-type": "application/json"},
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": {"maxOutputTokens": self.max_output_tokens}})
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        usage = data.get("usageMetadata") or {}
        return LLMResult(text="".join(p.get("text", "") for p in parts),
                         prompt_tokens=int(usage.get("promptTokenCount") or 0),
                         completion_tokens=int(usage.get("candidatesTokenCount") or 0))


def _build(name: str, s) -> LLMProvider:
    if name == "ollama":
        return OllamaProvider(s.ollama_url, s.ollama_model)
    if name == "mock":
        return MockProvider()
    if name == "claude":
        return ClaudeProvider(s.anthropic_api_key, s.anthropic_model, s.anthropic_base_url,
                              s.anthropic_input_usd_per_mtok, s.anthropic_output_usd_per_mtok, s.ai_max_output_tokens)
    if name == "gemini":
        return GeminiProvider(s.gemini_api_key, s.gemini_model, s.gemini_base_url,
                              s.gemini_input_usd_per_mtok, s.gemini_output_usd_per_mtok, s.ai_max_output_tokens)
    raise ValueError(f"LLM_PROVIDER desconhecido: {name!r} (use 'mock', 'ollama', 'claude' ou 'gemini')")


def get_provider() -> LLMProvider:
    return _build(get_settings().llm_provider, get_settings())


def get_fallback_provider() -> LLMProvider | None:
    """Reserva GRATUITA usada quando o provedor pago está bloqueado. Só 'ollama': 'mock' devolveria texto de teste
    como se fosse trabalho, e um pago como reserva anularia a guarda de orçamento."""
    name = get_settings().llm_fallback_provider
    if not name:
        return None
    if name != "ollama":
        raise ValueError(f"LLM_FALLBACK_PROVIDER inválido: {name!r} (use vazio ou 'ollama')")
    return _build(name, get_settings())
