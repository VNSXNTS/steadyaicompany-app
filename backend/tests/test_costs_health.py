import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.entities import AIUsage, TaskStatus
from app.services import ceo, costs
from app.services.llm import LLMProvider, LLMResult, MockProvider, OllamaProvider
from app.services.tasks import TaskError, create_task, run_task


class PaidProvider(LLMProvider):
    """Provedor pago fictício: 1 dólar por milhão de tokens de saída."""
    name = "paid-test"
    model = "paid-1"
    paid = True

    def __init__(self):
        self.calls = 0

    def complete(self, system, prompt):
        self.calls += 1
        return LLMResult(text="resposta", prompt_tokens=1000, completion_tokens=2_000_000)

    def cost_micro_usd(self, prompt_tokens, completion_tokens):
        return completion_tokens  # 2_000_000 micro-USD = US$ 2,00


def test_paid_provider_blocked_without_budget(db, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
    t = create_task(db, "market_hunter", "pesquisar")
    p = PaidProvider()
    with pytest.raises(TaskError, match="orçamento"):
        run_task(db, t, p)
    assert p.calls == 0                      # nada foi consumido
    assert t.status == TaskStatus.PENDING    # e a tarefa continua na fila
    assert db.query(AIUsage).count() == 0


def test_paid_provider_runs_within_budget_and_stops_when_spent(db, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "3")
    p = PaidProvider()
    a = create_task(db, "market_hunter", "primeira")
    b = create_task(db, "strategy", "segunda")
    c = create_task(db, "cfo", "terceira")
    run_task(db, a, p)          # gasta US$ 2 de 3
    run_task(db, b, p)          # ainda cabe (2 < 3); passa a US$ 4
    assert costs.month_spend_micro_usd(db) == 4_000_000
    with pytest.raises(TaskError):  # estourou: bloqueia
        run_task(db, c, p)
    assert p.calls == 2


def test_run_all_stops_quietly_when_budget_blocks(db, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
    create_task(db, "market_hunter", "x")
    assert ceo.run_until_blocked(db, PaidProvider()) == []


def test_free_provider_records_usage_with_zero_cost(db):
    t = create_task(db, "market_hunter", "pesquisar")
    run_task(db, t, MockProvider())
    u = db.query(AIUsage).one()
    assert (u.provider, u.cost_micro_usd, u.ok, u.task_id) == ("mock", 0, True, t.id)


def test_failed_call_is_recorded(db):
    class Boom(LLMProvider):
        name = "boom"

        def complete(self, system, prompt):
            raise RuntimeError("fora do ar")

    t = create_task(db, "market_hunter", "x")
    run_task(db, t, Boom())
    u = db.query(AIUsage).one()
    assert u.ok is False and u.provider == "boom"


def test_costs_endpoint(client, db):
    t = create_task(db, "market_hunter", "x")
    run_task(db, t, MockProvider())
    d = client.get("/costs").json()
    assert d["calls"] == 1 and d["failed_calls"] == 0 and d["spend_usd"] == 0
    assert d["paid_providers_allowed"] is False and d["budget_used_percent"] is None
    assert d["by_provider"][0]["provider"] == "mock"


def test_ollama_check_reports_unreachable():
    ok, detail = OllamaProvider("http://127.0.0.1:9", "llama3.2").check()  # porta fechada
    assert ok is False and "inacessível" in detail


def test_provider_status_endpoint_mock(client):
    d = client.get("/providers/status").json()
    assert d["provider"] == "mock" and d["ok"] is True and d["paid"] is False


def test_provider_status_unknown_provider(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "inexistente")
    d = client.get("/providers/status").json()
    assert d["ok"] is False and "desconhecido" in d["detail"]


def test_settings_hide_secrets(client):
    d = client.get("/settings").json()
    assert d["admin_key_configured"] is True
    assert "test-key" not in str(d)
    assert d["database_dialect"] == "sqlite"
    assert d["integrations"]["telegram"] == "não implementado"


def test_health_is_public_and_reports_database(client):
    with TestClient(app) as anon:
        d = anon.get("/health").json()
    assert d["status"] == "ok" and d["database"] == "ok"


def test_series_is_zero_without_data_and_counts_real_data(client):
    empty = client.get("/dashboard/series?days=7").json()["days"]
    assert len(empty) == 7 and all(p["net_revenue_cents"] == 0 and p["expenses_cents"] == 0 for p in empty)
    client.post("/sales", json={"gross_cents": 1000, "fee_cents": 100, "refunded_cents": 0})
    client.post("/expenses", json={"category": "ads", "amount_cents": 250})
    last = client.get("/dashboard/series?days=7").json()["days"][-1]
    assert last["net_revenue_cents"] == 900 and last["expenses_cents"] == 250


def test_agents_stats(client):
    client.post("/tasks", json={"agent_key": "cfo", "description": "relatório mensal"})
    stats = {r["agent_key"]: r for r in client.get("/agents-stats").json()}
    assert len(stats) == 13 and stats["cfo"]["pending"] == 1 and stats["ceo"]["pending"] == 0


def test_request_logging_has_no_secrets(client, caplog):
    with caplog.at_level(logging.INFO, logger="steady.http"):
        client.get("/agents")
    rec = [r for r in caplog.records if r.name == "steady.http"][-1]
    assert rec.path == "/agents" and rec.status == 200 and rec.request_id
    assert "test-key" not in rec.getMessage() and "test-key" not in str(rec.__dict__)
