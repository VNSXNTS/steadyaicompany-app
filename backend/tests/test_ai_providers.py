"""Fase 9: provedores de IA contra servidores HTTP LOCAIS FALSOS (imitam o formato de Ollama, Claude e Gemini).

Isto exercita o nosso cliente (httpx, cabeçalhos, JSON, tokens, custo, guarda de orçamento, fallback). NÃO prova que
os serviços reais respondem assim: isso depende de rodar `scripts/check_ollama.py` e de uma chamada paga real.
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.models.entities import AIUsage, AuditLog, TaskLog, TaskStatus
from app.services import costs
from app.services.llm import ClaudeProvider, GeminiProvider, OllamaProvider, get_fallback_provider, get_provider
from app.services.tasks import TaskError, create_task, run_task

SECRET = "sk-test-SEGREDO-123"


class Fake:
    """Servidor HTTP em thread. `routes` mapeia (método, caminho) -> (status, corpo JSON)."""

    def __init__(self, routes):
        self.routes, self.requests = routes, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(n) or b"null") if n else None
                outer.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers),
                                       "body": body})
                status, payload = outer.routes.get((self.command, self.path), (404, {"error": "x"}))
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = _do

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def fake():
    made = []

    def make(routes):
        f = Fake(routes)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


OLLAMA_OK = {("GET", "/api/tags"): (200, {"models": [{"name": "llama3.2:latest"}]}),
             ("POST", "/api/generate"): (200, {"response": "ok!", "prompt_eval_count": 11, "eval_count": 3})}
CLAUDE_OK = {("POST", "/v1/messages"): (200, {"content": [{"type": "text", "text": "Olá "}, {"type": "text", "text": "mundo"}],
                                              "usage": {"input_tokens": 100, "output_tokens": 50}})}
GEMINI_PATH = "/v1beta/models/gem-1:generateContent"
GEMINI_OK = {("POST", GEMINI_PATH): (200, {"candidates": [{"content": {"parts": [{"text": "Oi"}, {"text": "!"}]}}],
                                            "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2}})}


def claude(url, **kw):
    a = dict(api_key=SECRET, model="m-1", base_url=url, in_price=3.0, out_price=15.0, max_output_tokens=500)
    a.update(kw)
    return ClaudeProvider(**a)


def gemini(url, **kw):
    a = dict(api_key=SECRET, model="gem-1", base_url=url, in_price=0.5, out_price=2.0, max_output_tokens=500)
    a.update(kw)
    return GeminiProvider(**a)


# ---- Ollama (protocolo) ----
def test_ollama_protocol_check_and_complete(fake):
    f = fake(OLLAMA_OK)
    p = OllamaProvider(f.url, "llama3.2")
    assert p.check() == (True, "Ollama ok com o modelo 'llama3.2'")
    r = p.complete("sistema", "pergunta")
    assert (r.text, r.prompt_tokens, r.completion_tokens) == ("ok!", 11, 3)
    body = f.requests[-1]["body"]
    assert body == {"model": "llama3.2", "system": "sistema", "prompt": "pergunta", "stream": False}


def test_ollama_model_missing_and_server_error(fake):
    f = fake({("GET", "/api/tags"): (200, {"models": [{"name": "outro:1b"}]}), ("POST", "/api/generate"): (500, {})})
    ok, detail = OllamaProvider(f.url, "llama3.2").check()
    assert ok is False and "não está instalado" in detail
    with pytest.raises(Exception):
        OllamaProvider(f.url, "llama3.2").complete("s", "p")


# ---- Claude ----
def test_claude_request_shape_tokens_and_cost(fake):
    f = fake(CLAUDE_OK)
    p = claude(f.url)
    r = p.complete("sys", "pergunta")
    req = f.requests[0]
    assert req["path"] == "/v1/messages" and req["headers"]["x-api-key"] == SECRET
    assert req["headers"]["anthropic-version"] == "2023-06-01"
    assert req["body"] == {"model": "m-1", "max_tokens": 500, "system": "sys",
                           "messages": [{"role": "user", "content": "pergunta"}]}
    assert (r.text, r.prompt_tokens, r.completion_tokens) == ("Olá mundo", 100, 50)
    assert p.cost_micro_usd(100, 50) == 100 * 3 + 50 * 15 == 1050  # US$/milhão == micro-US$/token


def test_cost_rounds_up_never_down():
    p = claude("http://x", in_price=0.3, out_price=0.3)
    assert p.cost_micro_usd(1, 0) == 1  # 0.3 micro-US$ vira 1: a conta nunca subestima


# ---- Gemini ----
def test_gemini_request_shape_tokens_and_cost(fake):
    f = fake(GEMINI_OK)
    p = gemini(f.url)
    r = p.complete("sys", "pergunta")
    req = f.requests[0]
    assert req["path"] == GEMINI_PATH and req["headers"]["x-goog-api-key"] == SECRET
    assert SECRET not in req["path"]  # chave no cabeçalho, nunca na URL
    assert req["body"]["generationConfig"] == {"maxOutputTokens": 500}
    assert req["body"]["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert (r.text, r.prompt_tokens, r.completion_tokens) == ("Oi!", 7, 2)
    assert p.cost_micro_usd(7, 2) == 7 * 0.5 + 2 * 2.0 + 0.5 and p.cost_micro_usd(7, 2) == 8  # ceil(7.5)


# ---- configuração obrigatória ----
@pytest.mark.parametrize("kw,missing", [({"api_key": ""}, "chave"), ({"model": ""}, "modelo"),
                                        ({"in_price": 0.0}, "preços"), ({"out_price": 0.0}, "preços")])
def test_paid_provider_blocked_without_key_model_or_prices(kw, missing):
    p = claude("http://x", **kw)
    assert missing in p.blocked_reason()
    ok, detail = p.check()
    assert ok is False and missing in detail
    with pytest.raises(RuntimeError):  # nem a chamada direta contorna a guarda
        p.complete("s", "p")


def test_http_error_does_not_leak_body_or_key(fake):
    f = fake({("POST", "/v1/messages"): (401, {"error": f"chave {SECRET} inválida"})})
    with pytest.raises(RuntimeError) as e:
        claude(f.url).complete("s", "p")
    assert "401" in str(e.value) and SECRET not in str(e.value)


def test_paid_check_never_calls_the_network(fake):
    f = fake(CLAUDE_OK)
    ok, detail = claude(f.url).check()
    assert ok is True and "NÃO testado" in detail and f.requests == []


# ---- guarda de orçamento com provedor pago real (cliente) ----
def test_budget_zero_blocks_before_any_http_call(db, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
    f = fake(CLAUDE_OK)
    t = create_task(db, "market_hunter", "pesquisar")
    with pytest.raises(TaskError, match="orçamento"):
        run_task(db, t, claude(f.url))
    assert f.requests == [] and t.status == TaskStatus.PENDING and db.query(AIUsage).count() == 0


def test_missing_config_blocks_even_with_budget(db, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "50")
    f = fake(CLAUDE_OK)
    t = create_task(db, "market_hunter", "pesquisar")
    with pytest.raises(TaskError, match="faltam chave de API"):
        run_task(db, t, claude(f.url, api_key=""))
    assert f.requests == [] and t.status == TaskStatus.PENDING and t.attempts == 0


def test_worst_case_estimate_blocks_a_call_that_could_exceed_budget(db, fake, monkeypatch):
    # pior caso: ~1 token de entrada + 500 de saída a US$ 15/Mtok = 7503 micro-US$ > US$ 0,005
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0.005")
    f = fake(CLAUDE_OK)
    t = create_task(db, "market_hunter", "oi")
    with pytest.raises(TaskError, match="pior caso"):
        run_task(db, t, claude(f.url))
    assert f.requests == []
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0.01")  # agora cabe
    run_task(db, t, claude(f.url))
    assert t.status == TaskStatus.COMPLETED and len(f.requests) == 1


def test_worst_case_counts_a_long_prompt_too(db, fake, monkeypatch):
    # saída sozinha custa 500 * 15 = 7500; um prompt de 3000 caracteres (~1001 tokens * 3) leva o pior caso a 10503
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0.0078")
    f = fake(CLAUDE_OK)
    t = create_task(db, "market_hunter", "x" * 3000)
    with pytest.raises(TaskError, match="pior caso"):
        run_task(db, t, claude(f.url))
    assert f.requests == []
    short = create_task(db, "strategy", "oi")  # prompt curto no mesmo orçamento: cabe
    run_task(db, short, claude(f.url))
    assert short.status == TaskStatus.COMPLETED


def test_paid_call_records_real_cost_and_tokens(db, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "5")
    f = fake(GEMINI_OK)
    t = create_task(db, "market_hunter", "pesquisar")
    run_task(db, t, gemini(f.url))
    u = db.query(AIUsage).one()
    assert (u.provider, u.model, u.prompt_tokens, u.completion_tokens, u.cost_micro_usd, u.ok) == \
        ("gemini", "gem-1", 7, 2, 8, True)
    assert t.output["text"] == "Oi!"


def test_paid_http_failure_is_recorded_as_failed_usage_and_retried(db, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "5")
    f = fake({("POST", "/v1/messages"): (500, {})})
    t = create_task(db, "market_hunter", "pesquisar")
    run_task(db, t, claude(f.url))
    assert t.status == TaskStatus.PENDING and t.attempts == 1 and "HTTP 500" in t.error
    u = db.query(AIUsage).one()
    assert u.ok is False and u.cost_micro_usd == 0


# ---- fallback ----
def test_fallback_to_ollama_when_paid_is_blocked(db, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    o = fake(OLLAMA_OK)
    monkeypatch.setenv("OLLAMA_URL", o.url)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    c = fake(CLAUDE_OK)
    t = create_task(db, "market_hunter", "pesquisar")
    run_task(db, t, claude(c.url))
    assert t.status == TaskStatus.COMPLETED and t.output["provider"] == "ollama" and c.requests == []
    assert db.query(AIUsage).one().cost_micro_usd == 0
    log = db.query(TaskLog).filter(TaskLog.task_id == t.id, TaskLog.event == "fallback").one()
    assert "orçamento" in log.message and "ollama" in log.message


@pytest.mark.parametrize("name", ["mock", "claude", "xyz"])
def test_fallback_only_accepts_free_real_provider(db, monkeypatch, name):
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", name)
    with pytest.raises(ValueError, match="LLM_FALLBACK_PROVIDER"):
        get_fallback_provider()
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
    t = create_task(db, "market_hunter", "pesquisar")
    with pytest.raises(TaskError, match="reserva inválida"):
        run_task(db, t, claude("http://x"))
    assert t.status == TaskStatus.PENDING


def test_no_fallback_configured_keeps_task_pending(db, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
    monkeypatch.delenv("LLM_FALLBACK_PROVIDER", raising=False)
    t = create_task(db, "market_hunter", "pesquisar")
    with pytest.raises(TaskError):
        run_task(db, t, claude("http://x"))
    assert t.status == TaskStatus.PENDING


# ---- seleção, segredos e painel ----
def test_get_provider_selects_claude_and_gemini_from_env(monkeypatch):
    for name, cls in (("claude", ClaudeProvider), ("gemini", GeminiProvider)):
        monkeypatch.setenv("LLM_PROVIDER", name)
        p = get_provider()
        assert isinstance(p, cls) and p.paid is True
        assert "faltam" in p.blocked_reason()  # sem chave/modelo/preços nada roda


def test_empty_env_example_values_do_not_crash(monkeypatch):
    for k in ("ANTHROPIC_INPUT_USD_PER_MTOK", "GEMINI_OUTPUT_USD_PER_MTOK", "AI_MAX_OUTPUT_TOKENS"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    assert get_provider().max_output_tokens == 1024
    monkeypatch.setenv("ANTHROPIC_INPUT_USD_PER_MTOK", "abc")
    with pytest.raises(RuntimeError, match="ANTHROPIC_INPUT_USD_PER_MTOK"):
        get_provider()


def test_settings_endpoint_never_exposes_keys(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", SECRET + "g")
    r = client.get("/settings")
    assert SECRET not in r.text
    d = r.json()
    assert "faltam modelo, preços" in d["integrations"]["claude"] and "orçamento mensal" in d["integrations"]["claude"]
    assert d["llm_fallback_provider"] is None


def test_key_never_reaches_logs_or_task_records(db, fake, monkeypatch, caplog):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "5")
    f = fake({("POST", "/v1/messages"): (500, {"error": SECRET})})
    t = create_task(db, "market_hunter", "pesquisar")
    with caplog.at_level(logging.DEBUG):
        run_task(db, t, claude(f.url))
    blob = " ".join([caplog.text, str(t.error), str(t.output)] +
                    [str(x.message) for x in db.query(TaskLog).all()] + [str(x.detail) for x in db.query(AuditLog).all()])
    assert SECRET not in blob


def test_cost_panel_has_models_daily_and_remaining(db, client, fake, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "5")
    f = fake(CLAUDE_OK)
    run_task(db, create_task(db, "market_hunter", "a"), claude(f.url))
    run_task(db, create_task(db, "strategy", "b"), claude(f.url))
    d = client.get("/costs").json()
    assert d["by_model"] == [{"provider": "claude", "model": "m-1", "calls": 2, "spend_usd": 0.0021}]
    assert len(d["daily"]) == 1 and d["daily"][0]["calls"] == 2 and d["daily"][0]["spend_usd"] == 0.0021
    assert d["remaining_usd"] == round(5 - 0.0021, 6) and d["spend_usd"] == 0.0021


def test_cost_panel_remaining_is_null_without_budget(client):
    d = client.get("/costs").json()
    assert d["remaining_usd"] is None and d["by_model"] == [] and d["daily"] == []
