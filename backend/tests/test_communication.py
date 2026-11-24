"""Fase 8: mensagens e handoffs entre agentes (registro, auditoria e travas contra loop)."""
import pytest
from sqlalchemy import select, text

from app.models.entities import AgentMessage, AuditLog, Task, TaskLog, TaskStatus
from app.services import communication as comm
from app.services.tasks import TaskError, create_task, run_task


def done(db, agent="market_hunter", **inp):
    t = create_task(db, agent, "trabalho de teste", input={"tool": "financial_summary", **inp} if agent == "cfo" else inp)
    t.status = TaskStatus.COMPLETED
    db.commit()
    return t


# ---- mensagens ----
def test_message_is_recorded_audited_and_executes_nothing(db):
    before = db.query(Task).count()
    m = comm.send_message(db, "cfo", "ceo", "Margem baixa", "Detalhes", actor="admin")
    assert m.kind == "message" and m.hop == 0 and db.query(Task).count() == before
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "agent_message")).one()
    assert audit.detail["from"] == "cfo" and audit.detail["to"] == "ceo"


@pytest.mark.parametrize("kw", [dict(from_agent="cfo", to_agent="cfo"), dict(from_agent="x", to_agent="ceo"),
                                dict(from_agent="cfo", to_agent="y"), dict(from_agent="cfo", to_agent="ceo", subject=" "),
                                dict(from_agent="cfo", to_agent="ceo", body="x" * 4001),
                                dict(from_agent="cfo", to_agent="ceo", task_id=9999),
                                dict(from_agent="cfo", to_agent="ceo", parent_id=9999)])
def test_message_validation(db, kw):
    kw.setdefault("subject", "ok")
    with pytest.raises(TaskError):
        comm.send_message(db, kw.pop("from_agent"), kw.pop("to_agent"), kw.pop("subject"), kw.pop("body", ""), **kw)
    assert db.query(AgentMessage).count() == 0


def test_reply_chain_has_depth_limit(db):
    m = comm.send_message(db, "cfo", "ceo", "0")
    for i in range(comm.MAX_HANDOFF_DEPTH):
        m = comm.send_message(db, "ceo" if i % 2 == 0 else "cfo", "cfo" if i % 2 == 0 else "ceo", str(i + 1), parent_id=m.id)
    assert m.hop == comm.MAX_HANDOFF_DEPTH
    with pytest.raises(TaskError, match="acima do limite"):
        comm.send_message(db, "cfo", "ceo", "demais", parent_id=m.id)


# ---- handoff ----
def test_handoff_creates_dependent_task_with_trail_and_logs(db):
    a = done(db, "market_hunter")
    m = comm.handoff(db, a.id, "competitor_analyst", "Compare as ofertas", priority=2)
    new = db.get(Task, m.handoff_task_id)
    assert m.kind == "handoff" and m.from_agent == "market_hunter" and m.task_id == a.id and m.hop == 1
    assert new.agent_key == "competitor_analyst" and new.depends_on == [a.id] and new.status == TaskStatus.PENDING
    assert new.input["handoff"] == {"from_agent": "market_hunter", "from_task_id": a.id, "hop": 1,
                                    "path": ["market_hunter", "competitor_analyst"]}
    assert db.scalars(select(TaskLog.event).where(TaskLog.task_id == a.id, TaskLog.event == "handoff_sent")).first()
    assert db.scalars(select(TaskLog.event).where(TaskLog.task_id == new.id, TaskLog.event == "handoff_received")).first()
    assert db.scalars(select(AuditLog).where(AuditLog.action == "agent_handoff")).one().detail["new_task_id"] == new.id


def test_handoff_requires_completed_origin(db):
    t = create_task(db, "market_hunter", "ainda pendente")
    with pytest.raises(TaskError, match="concluídas"):
        comm.handoff(db, t.id, "cfo", "passe adiante")
    with pytest.raises(TaskError, match="inexistente"):
        comm.handoff(db, 9999, "cfo", "passe adiante")
    assert db.query(AgentMessage).count() == 0 and db.query(Task).count() == 1


def test_handoff_blocks_self_and_ping_pong_loops(db):
    a = done(db, "market_hunter")
    with pytest.raises(TaskError, match="si mesmo"):
        comm.handoff(db, a.id, "market_hunter", "volta")
    b = db.get(Task, comm.handoff(db, a.id, "competitor_analyst", "vai").handoff_task_id)
    b.status = TaskStatus.COMPLETED
    db.commit()
    with pytest.raises(TaskError, match="Loop bloqueado"):  # A -> B -> A
        comm.handoff(db, b.id, "market_hunter", "volta")
    c = db.get(Task, comm.handoff(db, b.id, "strategy", "segue").handoff_task_id)
    c.status = TaskStatus.COMPLETED
    db.commit()
    with pytest.raises(TaskError, match="Loop bloqueado"):  # A -> B -> C -> B
        comm.handoff(db, c.id, "competitor_analyst", "volta")


def test_handoff_depth_limit_on_a_long_chain(db):
    agents = ["market_hunter", "competitor_analyst", "strategy", "product_architect", "product_creator",
              "quality_guardian", "sales_manager"]
    t = done(db, agents[0])
    for nxt in agents[1:comm.MAX_HANDOFF_DEPTH + 1]:
        t = db.get(Task, comm.handoff(db, t.id, nxt, "segue").handoff_task_id)
        t.status = TaskStatus.COMPLETED
        db.commit()
    with pytest.raises(TaskError, match="Profundidade máxima"):
        comm.handoff(db, t.id, agents[-1], "demais")


def test_caller_cannot_forge_chain_or_grant_risky_action(db):
    a = done(db, "market_hunter")
    m = comm.handoff(db, a.id, "cfo", "x", input={"handoff": {"hop": 0, "path": []}, "action": "spend_money"})
    new = db.get(Task, m.handoff_task_id)
    assert new.input["handoff"]["hop"] == 1 and new.input["handoff"]["path"] == ["market_hunter", "cfo"]
    assert new.action is None and new.requires_approval is False  # handoff não concede ação


def test_handed_off_task_waits_for_origin_and_runs_afterwards(db):
    a = create_task(db, "cfo", "resumo", input={"tool": "financial_summary"})
    run_task(db, a)
    m = comm.handoff(db, a.id, "strategy", "analise", input={"tool": "experiment_review", "experiment_id": 1})
    new = db.get(Task, m.handoff_task_id)
    assert new.depends_on == [a.id] and new.status == TaskStatus.PENDING


# ---- API ----
def test_api_message_handoff_and_list_filters(client, db):
    a = done(db, "market_hunter")
    r = client.post("/agent-messages", json={"from_agent": "cfo", "to_agent": "ceo", "subject": "Oi", "task_id": a.id})
    assert r.status_code == 201 and r.json()["kind"] == "message"
    h = client.post("/handoffs", json={"from_task_id": a.id, "to_agent": "cfo", "description": "Resuma"})
    assert h.status_code == 201 and h.json()["handoff_task_id"]
    assert client.post("/handoffs", json={"from_task_id": a.id, "to_agent": "market_hunter",
                                          "description": "Resuma"}).status_code == 400
    assert len(client.get("/agent-messages").json()) == 2
    assert [m["kind"] for m in client.get("/agent-messages?kind=handoff").json()] == ["handoff"]
    assert len(client.get(f"/agent-messages?task_id={a.id}").json()) == 2
    assert len(client.get("/agent-messages?agent=ceo").json()) == 1


def test_api_requires_authentication(client):
    anon = client.__class__(client.app)
    for method, url, body in (("post", "/agent-messages", {}), ("post", "/handoffs", {}), ("get", "/agent-messages", None)):
        assert getattr(anon, method)(url, **({"json": body} if body is not None else {})).status_code == 401


def test_api_validation_errors_are_422_or_400(client):
    assert client.post("/agent-messages", json={"from_agent": "cfo", "to_agent": "ceo", "subject": ""}).status_code == 422
    assert client.post("/handoffs", json={"from_task_id": 999, "to_agent": "cfo", "description": "abc"}).status_code == 400
