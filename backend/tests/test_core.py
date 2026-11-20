import pytest

from app.models.entities import Agent, Approval, Product, Task, TaskStatus
from app.services import ceo
from app.services.agent_registry import AGENT_KEYS
from app.services.llm import LLMProvider, LLMResult, MockProvider
from app.services.tasks import TaskError, create_task, decide_approval, next_runnable, run_task


class FailingProvider(LLMProvider):
    name = "failing"

    def complete(self, system, prompt):
        raise RuntimeError("modelo indisponível")


class FlakyProvider(LLMProvider):
    name = "flaky"

    def __init__(self):
        self.calls = 0

    def complete(self, system, prompt):
        self.calls += 1
        if self.calls < 2:
            raise RuntimeError("falha temporária")
        return LLMResult(text="ok")


def test_seed_creates_13_agents_none_can_spend(db):
    agents = db.query(Agent).all()
    assert len(agents) == 13
    assert {a.key for a in agents} == set(AGENT_KEYS)
    assert not any(a.can_spend for a in agents)


def test_risky_action_forces_approval(db):
    t = create_task(db, "growth_strategist", "Publicar anúncios", action="publish_paid_ads")
    assert t.requires_approval is True
    assert t.status == TaskStatus.AWAITING_APPROVAL
    assert db.query(Approval).filter_by(task_id=t.id, status="pending").count() == 1
    # não pode rodar nem entrar na fila sem aprovação
    with pytest.raises(TaskError):
        run_task(db, t, MockProvider())
    assert next_runnable(db) is None


def test_safe_task_runs_without_approval(db):
    t = create_task(db, "market_hunter", "Pesquisar dores do público")
    assert t.requires_approval is False
    run_task(db, t, MockProvider())
    assert t.status == TaskStatus.COMPLETED
    assert t.output["provider"] == "mock"
    assert "MOCK" in t.output["text"]  # saída simulada é identificável


def test_approve_releases_task_and_reject_cancels(db):
    a = create_task(db, "cfo", "Pagar fornecedor", action="make_payment")
    b = create_task(db, "cfo", "Mudar preço", action="change_price")
    appr_a = db.query(Approval).filter_by(task_id=a.id).one()
    appr_b = db.query(Approval).filter_by(task_id=b.id).one()
    decide_approval(db, appr_a.id, "approved", "ok")
    decide_approval(db, appr_b.id, "rejected", "não")
    db.refresh(a), db.refresh(b)
    assert a.status == TaskStatus.PENDING
    assert b.status == TaskStatus.CANCELLED
    with pytest.raises(TaskError):  # não dá para decidir duas vezes
        decide_approval(db, appr_a.id, "rejected")


def test_dependencies_block_until_done(db):
    first = create_task(db, "market_hunter", "primeira")
    second = create_task(db, "strategy", "segunda", depends_on=[first.id])
    assert next_runnable(db).id == first.id
    with pytest.raises(TaskError):
        run_task(db, second, MockProvider())
    run_task(db, first, MockProvider())
    assert next_runnable(db).id == second.id


def test_paused_agent_does_not_run(db):
    t = create_task(db, "market_hunter", "pesquisar")
    db.get(Agent, "market_hunter").status = "paused"
    db.commit()
    assert next_runnable(db) is None
    with pytest.raises(TaskError):
        run_task(db, t, MockProvider())


def test_retries_then_fails(db):
    t = create_task(db, "market_hunter", "pesquisar")
    for _ in range(3):
        run_task(db, t, FailingProvider())
    assert t.status == TaskStatus.FAILED
    assert t.attempts == 3
    assert "modelo indisponível" in t.error


def test_retry_recovers(db):
    t = create_task(db, "market_hunter", "pesquisar")
    p = FlakyProvider()
    run_task(db, t, p)
    assert t.status == TaskStatus.PENDING and t.attempts == 1
    run_task(db, t, p)
    assert t.status == TaskStatus.COMPLETED and t.error is None


def test_invalid_inputs_rejected(db):
    with pytest.raises(TaskError):
        create_task(db, "agente_inexistente", "x")
    with pytest.raises(TaskError):
        create_task(db, "cfo", "x", priority=9)
    with pytest.raises(TaskError):
        create_task(db, "cfo", "x", depends_on=[999])


def test_ceo_pipeline_stops_at_approval(db):
    tasks = ceo.plan_goal(db, "debt planner for freelancers")
    assert len(tasks) == 10
    ran = ceo.run_until_blocked(db, MockProvider())
    assert len(ran) == 9  # tudo menos a publicação paga
    last = db.get(Task, tasks[-1].id)
    assert last.status == TaskStatus.AWAITING_APPROVAL
    report = ceo.executive_report(db)
    assert report["pending_approvals"] == 1
    assert report["attention_needed"] is True
    # aprovando, a última etapa passa a rodar
    appr = db.query(Approval).filter_by(task_id=last.id).one()
    decide_approval(db, appr.id, "approved")
    ceo.run_until_blocked(db, MockProvider())
    db.refresh(last)
    assert last.status == TaskStatus.COMPLETED


def test_publish_only_after_approval(db):
    p = Product(name="Steady Payoff", price_cents=900)
    db.add(p)
    db.commit()
    from app.models.entities import Approval as A
    a = A(action="publish_commercial_change", details={"product_id": p.id})
    db.add(a)
    db.commit()
    db.refresh(p)
    assert p.status != "published"
    decide_approval(db, a.id, "approved")
    db.refresh(p)
    assert p.status == "published"
