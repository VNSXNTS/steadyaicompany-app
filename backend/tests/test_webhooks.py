"""Fase 10: webhooks autenticados do n8n (segredo próprio, idempotência, escopo mínimo)."""
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import webhooks
from app.main import app
from app.models.entities import Approval, AuditLog, Task, TaskStatus, WebhookReceipt
from app.services.tasks import create_task

SECRET = "n8n-segredo-forte-com-mais-de-32-caracteres!"
H = {"X-Webhook-Secret": SECRET}
BODY = {"agent_key": "creative_director", "description": "Checar criativo",
        "input": {"tool": "creative_check", "headline": "Plan your payoff", "body": "Results vary."}}


@pytest.fixture()
def wh(db, monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", SECRET)
    with TestClient(app) as c:  # sem X-API-Key nem cookie: só o segredo do webhook conta
        yield c


def post(c, key="chave-0001-abc", body=None, headers=None):
    return c.post("/webhooks/n8n/tasks", json=body or BODY, headers={**H, "Idempotency-Key": key, **(headers or {})})


# ---- autenticação ----
@pytest.mark.parametrize("secret", ["", "curto", "x" * 31])
def test_webhooks_are_off_without_a_strong_secret(db, monkeypatch, secret):
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", secret)
    with TestClient(app) as c:
        r = c.get("/webhooks/n8n/report", headers={"X-Webhook-Secret": secret})
    assert r.status_code == 503 and "N8N_WEBHOOK_SECRET" in r.json()["detail"]


def test_missing_or_wrong_secret_is_401_and_audited_without_the_value(wh, db):
    assert wh.get("/webhooks/n8n/report").status_code == 401
    r = wh.get("/webhooks/n8n/report", headers={"X-Webhook-Secret": "errado-errado-errado-errado-errado-1"})
    assert r.status_code == 401
    assert "errado" not in str([a.detail for a in db.scalars(select(AuditLog)).all()])
    assert db.query(AuditLog).filter_by(action="webhook_denied").count() == 2


def test_admin_credentials_do_not_open_webhooks_and_secret_does_not_open_panel(wh):
    assert wh.get("/webhooks/n8n/report", headers={"X-API-Key": "test-key"}).status_code == 401
    assert wh.get("/tasks", headers=H).status_code in (401, 503)  # o segredo do n8n não vale no painel
    assert wh.get("/approvals", headers=H).status_code in (401, 503)


def test_session_cookie_does_not_open_webhooks(wh, db):
    wh.cookies.set("steady_session", "qualquer")
    assert wh.get("/webhooks/n8n/report").status_code == 401


# ---- criar tarefa ----
def test_create_task_201_with_audit_receipt_and_actor(wh, db):
    r = post(wh)
    assert r.status_code == 201 and r.json()["duplicate"] is False
    t = db.get(Task, r.json()["id"])
    assert t.agent_key == "creative_director" and t.status == TaskStatus.PENDING and t.action is None
    assert db.get(WebhookReceipt, "chave-0001-abc").task_id == t.id
    assert db.query(AuditLog).filter_by(action="webhook_task_created", actor="n8n").count() == 1


def test_same_idempotency_key_returns_same_task_without_duplicating(wh, db):
    first = post(wh).json()
    second = post(wh)
    assert second.status_code == 200 and second.json()["duplicate"] is True and second.json()["id"] == first["id"]
    assert db.query(Task).count() == 1


def test_idempotency_key_required_and_validated(wh):
    for key in (None, "curta", "tem espaco aqui", "x" * 101):
        h = dict(H) if key is None else {**H, "Idempotency-Key": key}
        assert wh.post("/webhooks/n8n/tasks", json=BODY, headers=h).status_code == 400, key


def test_in_flight_key_gets_409_not_a_second_task(wh, db):
    db.add(WebhookReceipt(key="chave-corrida-1", source="n8n"))  # reservada, tarefa ainda não criada
    db.commit()
    assert post(wh, key="chave-corrida-1").status_code == 409
    assert db.query(Task).count() == 0


def test_action_and_unknown_fields_are_rejected_so_no_risky_action_via_webhook(wh, db):
    for extra in ({"action": "spend_money"}, {"requires_approval": False}, {"status": "completed"}):
        assert post(wh, key=f"k-{list(extra)[0]}-1", body={**BODY, **extra}).status_code == 422
    assert db.query(Task).count() == 0 and db.query(Approval).count() == 0


def test_reserved_handoff_key_is_stripped_from_input(wh, db):
    body = {**BODY, "input": {**BODY["input"], "handoff": {"hop": 0, "path": []}}}
    t = db.get(Task, post(wh, key="chave-handoff-1", body=body).json()["id"])
    assert "handoff" not in t.input and t.input["tool"] == "creative_check"


def test_oversized_input_is_refused_before_creating_anything(wh, db):
    body = {**BODY, "input": {"x": "a" * (webhooks.MAX_INPUT_CHARS + 1)}}
    assert post(wh, key="chave-grande-1", body=body).status_code == 400
    assert db.query(Task).count() == 0 and db.query(WebhookReceipt).count() == 0


def test_invalid_agent_releases_the_key_so_a_corrected_retry_works(wh, db):
    bad = post(wh, key="chave-retry-01", body={**BODY, "agent_key": "nao_existe"})
    assert bad.status_code == 400 and "desconhecido" in bad.json()["detail"]
    assert db.get(WebhookReceipt, "chave-retry-01") is None
    assert post(wh, key="chave-retry-01").status_code == 201


@pytest.mark.parametrize("patch", [{"description": "ab"}, {"priority": 9}, {"agent_key": 5}])
def test_schema_validation_422(wh, patch):
    assert post(wh, key="chave-schema-1", body={**BODY, **patch}).status_code == 422


# ---- ler tarefa ----
def test_get_task_only_for_tasks_created_via_webhook(wh, db):
    tid = post(wh).json()["id"]
    other = create_task(db, "cfo", "criada pelo painel")
    assert wh.get(f"/webhooks/n8n/tasks/{tid}", headers=H).json()["id"] == tid
    assert wh.get(f"/webhooks/n8n/tasks/{other.id}", headers=H).status_code == 404
    assert wh.get("/webhooks/n8n/tasks/9999", headers=H).status_code == 404


# ---- relatório e aprovações ----
def test_report_matches_ceo_executive_report(wh, db):
    d = wh.get("/webhooks/n8n/report", headers=H).json()
    assert set(d) >= {"tasks_by_status", "pending_approvals", "failed_tasks", "attention_needed"}


def test_pending_approvals_exposes_only_the_minimum(wh, db):
    create_task(db, "sales_manager", "Pagar anúncio", action="spend_money", input={"amount": 10, "segredo": "x"})
    d = wh.get("/webhooks/n8n/approvals/pending", headers=H).json()
    assert d["count"] == 1
    a = d["approvals"][0]
    assert set(a) == {"id", "task_id", "action", "consequences", "agent", "description", "created_at"}
    assert a["action"] == "spend_money" and a["agent"] == "sales_manager" and "segredo" not in str(d)


def test_webhook_cannot_approve_or_run(wh):
    assert wh.post("/webhooks/n8n/approvals/1/decide", json={}, headers=H).status_code in (404, 405)
    assert wh.post("/webhooks/n8n/run", headers=H).status_code in (404, 405)


def test_secret_never_appears_in_responses_or_logs(wh, caplog):
    with caplog.at_level(logging.DEBUG):
        r1 = post(wh)
        r2 = wh.get("/webhooks/n8n/report", headers={"X-Webhook-Secret": "errado-errado-errado-errado-errado-1"})
    assert SECRET not in r1.text + r2.text + caplog.text
