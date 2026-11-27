"""Telegram (Fase 12): segurança do bot, aprovação em duas etapas, avisos e sigilo do token. Servidor da API é FALSO."""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import select

from app.models.entities import Approval, AuditLog, Experiment, Product, Task
from app.services import telegram_bot as tg

TOKEN = "123456:ABC-fake-token-for-tests"
OWNER, OTHER, STRANGER = 1001, 1002, 9999


class FakeClient:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send_message(self, chat_id, text):
        if self.fail:
            raise tg.TelegramError("sendMessage: HTTP 500")
        self.sent.append((chat_id, text))


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", f"{OWNER},{OTHER}")
    tg._confirmations.clear()


def upd(uid, text, *, chat_type="private", chat_id=None, bot=False):
    return {"update_id": 1, "message": {"from": {"id": uid, "is_bot": bot}, "chat": {"id": uid if chat_id is None else chat_id, "type": chat_type}, "text": text}}


def make_publish_approval(db):
    p = Product(name="Steady Payoff", description="x", price_cents=1900, status="draft")
    db.add(p); db.flush()
    a = Approval(action="publish_commercial_change", details={"product_id": p.id}, consequences="Publica o produto.")
    db.add(a); db.commit()
    return p, a


def say(db, uid, text, c=None):
    c = c or FakeClient()
    tg.handle_update(db, c, upd(uid, text))
    return c.sent[-1][1] if c.sent else None


# ---------- quem pode falar com o bot ----------
def test_stranger_gets_nothing_but_can_learn_own_id(db):
    p, a = make_publish_approval(db)
    c = FakeClient()
    tg.handle_update(db, c, upd(STRANGER, "/pendentes"))
    tg.handle_update(db, c, upd(STRANGER, f"/aprovar {a.id}"))
    assert c.sent == []
    tg.handle_update(db, c, upd(STRANGER, "/id"))
    assert str(STRANGER) in c.sent[0][1] and "TELEGRAM_ALLOWED_USER_IDS" in c.sent[0][1]
    assert db.scalars(select(AuditLog).where(AuditLog.action == "telegram_denied")).all()
    db.refresh(a); assert a.status == "pending"


def test_empty_allow_list_ignores_everyone_even_the_owner(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "")
    c = FakeClient()
    tg.handle_update(db, c, upd(OWNER, "/pendentes"))
    assert c.sent == []
    tg.handle_update(db, c, upd(OWNER, "/id"))  # só para descobrir o ID
    assert len(c.sent) == 1


@pytest.mark.parametrize("u", [
    upd(OWNER, "/pendentes", chat_type="group", chat_id=-500),
    upd(OWNER, "/pendentes", chat_type="supergroup"),
    upd(OWNER, "/pendentes", chat_id=555),  # chat diferente do usuário
    upd(OWNER, "/pendentes", bot=True),
])
def test_groups_other_chats_and_bots_are_never_served(db, u):
    c = FakeClient(); tg.handle_update(db, c, u); assert c.sent == []


@pytest.mark.parametrize("u", [None, [], {}, {"message": None}, {"message": {}}, {"message": {"text": 5}},
                               {"message": {"from": {"id": "1"}, "chat": {"id": 1, "type": "private"}, "text": "/id"}},
                               {"message": {"from": {"id": OWNER}, "chat": {"id": OWNER, "type": "private"}}}])
def test_malformed_updates_do_not_crash(db, u):
    c = FakeClient(); tg.handle_update(db, c, u); assert c.sent == []


# ---------- aprovação em duas etapas ----------
def test_approve_needs_the_code_and_then_really_publishes(db):
    p, a = make_publish_approval(db)
    msg = say(db, OWNER, f"/aprovar {a.id}")
    db.refresh(a); db.refresh(p)
    assert a.status == "pending" and p.status == "draft"  # só pedir não aprova
    code = msg.split(f"/confirmar {a.id} ")[1].split()[0]
    assert len(code) == 4 and code.isdigit()
    assert "APROVADA" in say(db, OWNER, f"/confirmar {a.id} {code}")
    db.refresh(a); db.refresh(p)
    assert a.status == "approved" and p.status == "published" and "Telegram" in a.decision_note
    assert db.scalars(select(AuditLog).where(AuditLog.action == "telegram_decision")).one().actor == f"telegram:{OWNER}"


def test_wrong_code_fails_and_burns_the_request(db):
    p, a = make_publish_approval(db)
    msg = say(db, OWNER, f"/aprovar {a.id}")
    code = msg.split(f"/confirmar {a.id} ")[1].split()[0]
    bad = "0000" if code != "0000" else "1111"
    assert "errado" in say(db, OWNER, f"/confirmar {a.id} {bad}")
    assert "Sem pedido" in say(db, OWNER, f"/confirmar {a.id} {code}")  # o código certo também morreu
    db.refresh(a); assert a.status == "pending"


def test_code_expires(db):
    p, a = make_publish_approval(db)
    c = FakeClient()
    msg = tg.handle_command(db, OWNER, f"/aprovar {a.id}", now=1000.0)
    code = msg.split(f"/confirmar {a.id} ")[1].split()[0]
    assert "expirou" in tg.handle_command(db, OWNER, f"/confirmar {a.id} {code}", now=1000.0 + tg.CONFIRM_TTL_SECONDS + 1)
    db.refresh(a); assert a.status == "pending"


def test_code_is_bound_to_user_approval_and_single_use(db):
    p, a = make_publish_approval(db)
    p2, a2 = make_publish_approval(db)
    msg = say(db, OWNER, f"/aprovar {a.id}")
    code = msg.split(f"/confirmar {a.id} ")[1].split()[0]
    assert "Sem pedido" in say(db, OTHER, f"/confirmar {a.id} {code}")      # outro usuário
    assert "Sem pedido" in say(db, OWNER, f"/confirmar {a2.id} {code}")     # outra aprovação
    db.refresh(a); db.refresh(a2); assert a.status == "pending" and a2.status == "pending"
    code = say(db, OWNER, f"/aprovar {a.id}").split(f"/confirmar {a.id} ")[1].split()[0]
    say(db, OWNER, f"/confirmar {a.id} {code}")
    assert "Sem pedido" in say(db, OWNER, f"/confirmar {a.id} {code}")      # uso único


def test_confirm_without_request_does_nothing(db):
    p, a = make_publish_approval(db)
    assert "Sem pedido" in say(db, OWNER, f"/confirmar {a.id} 1234")
    db.refresh(a); assert a.status == "pending"


def test_reject_is_immediate_and_cancels_the_task(db):
    t = Task(agent_key="growth_strategist", department="growth", description="x", status="awaiting_approval"); db.add(t); db.flush()
    a = Approval(task_id=t.id, action="publish_paid_ads", details={}, consequences="Gasta dinheiro."); db.add(a); db.commit()
    assert "REJEITADA" in say(db, OWNER, f"/rejeitar {a.id}")
    db.refresh(a); db.refresh(t)
    assert a.status == "rejected" and t.status == "cancelled"


def test_request_changes_needs_a_reason_and_stores_it(db):
    p, a = make_publish_approval(db)
    assert "Diga o que mudar" in say(db, OWNER, f"/alterar {a.id}")
    say(db, OWNER, f"/alterar {a.id} " + "x" * 900)
    db.refresh(a); assert a.status == "changes_requested" and len(a.decision_note) == 500


def test_already_decided_approval_is_reported_not_redone(db):
    p, a = make_publish_approval(db)
    say(db, OWNER, f"/rejeitar {a.id}")
    assert "já está" in say(db, OWNER, f"/aprovar {a.id}")
    assert "Não foi possível" in say(db, OWNER, f"/rejeitar {a.id}")


def test_experiment_gate_still_blocks_approval_from_telegram(db):
    e = Experiment(name="T", market="US", currency="USD", price_cents=1900, budget_cap_cents=5000,
                   max_spend_without_sale_cents=2000, min_sales_to_decide=3, status="pending_approval")
    db.add(e); db.flush()
    a = Approval(action="activate_campaign", details={"experiment_id": e.id}, consequences="Autoriza gasto."); db.add(a); db.commit()
    code = say(db, OWNER, f"/aprovar {a.id}").split(f"/confirmar {a.id} ")[1].split()[0]
    out = say(db, OWNER, f"/confirmar {a.id} {code}")
    assert "Não foi possível" in out and "bloqueada" in out.lower()
    db.refresh(a); db.refresh(e); assert a.status == "pending" and e.status == "pending_approval"


@pytest.mark.parametrize("text,expect", [("/ver", "Informe o número"), ("/aprovar abc", "Informe o número"), ("/ver 999", "não encontrada"),
                                          ("/xyz", "Não entendi"), ("/ajuda", "Comandos"), ("oi", "Não entendi")])
def test_bad_input_gets_a_helpful_answer(db, text, expect):
    assert expect in say(db, OWNER, text)


def test_pendentes_lists_and_empty_state(db):
    assert "Nenhuma aprovação pendente" in say(db, OWNER, "/pendentes")
    p, a = make_publish_approval(db)
    out = say(db, OWNER, "/pendentes")
    assert f"#{a.id}" in out and "Publica o produto." in out


# ---------- avisos ----------
def test_notify_sends_once_per_approval_to_every_allowed_user(db):
    p, a = make_publish_approval(db)
    c = FakeClient()
    assert tg.notify_pending(db, c) == 1
    assert sorted(x[0] for x in c.sent) == [OWNER, OTHER]
    assert tg.notify_pending(db, c) == 0 and len(c.sent) == 2
    p2, a2 = make_publish_approval(db)
    assert tg.notify_pending(db, c) == 1 and len(c.sent) == 4


def test_failed_notification_is_retried_not_lost(db):
    p, a = make_publish_approval(db)
    assert tg.notify_pending(db, FakeClient(fail=True)) == 0
    c = FakeClient()
    assert tg.notify_pending(db, c) == 1 and len(c.sent) == 2


def test_no_notification_without_allowed_users_or_for_decided_approvals(db, monkeypatch):
    p, a = make_publish_approval(db)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "")
    c = FakeClient(); assert tg.notify_pending(db, c) == 0 and c.sent == []
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(OWNER))
    say(db, OWNER, f"/rejeitar {a.id}")
    assert tg.notify_pending(db, c) == 0


# ---------- cliente HTTP contra servidor FALSO ----------
class _Fake(BaseHTTPRequestHandler):
    calls: list = []
    status = 200
    body = {"ok": True, "result": []}

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _Fake.calls.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
        self.send_response(_Fake.status); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(_Fake.body).encode())

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    _Fake.calls, _Fake.status, _Fake.body = [], 200, {"ok": True, "result": []}
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_client_sends_plain_text_truncated_to_the_right_endpoint(server):
    c = tg.TelegramClient(TOKEN, server)
    c.send_message(OWNER, "a" * 9000)
    path, body = _Fake.calls[0]
    assert path == f"/bot{TOKEN}/sendMessage"
    assert body["chat_id"] == OWNER and len(body["text"]) == tg.MAX_TEXT and "parse_mode" not in body


def test_get_updates_passes_offset_and_only_messages(server):
    _Fake.body = {"ok": True, "result": [{"update_id": 5}]}
    assert tg.TelegramClient(TOKEN, server).get_updates(6, 1) == [{"update_id": 5}]
    body = _Fake.calls[0][1]
    assert body["offset"] == 6 and body["allowed_updates"] == ["message"]


@pytest.mark.parametrize("status,body", [(401, {"ok": False}), (500, {}), (200, {"ok": False, "description": "x"})])
def test_errors_never_carry_the_token(server, caplog, status, body):
    _Fake.status, _Fake.body = status, body
    with pytest.raises(tg.TelegramError) as ei:
        tg.TelegramClient(TOKEN, server).send_message(OWNER, "oi")
    assert TOKEN not in str(ei.value) and "127.0.0.1" not in str(ei.value)
    assert TOKEN not in caplog.text


def test_network_failure_hides_token_and_url(caplog):
    with pytest.raises(tg.TelegramError) as ei:
        tg.TelegramClient(TOKEN, "http://127.0.0.1:1", timeout=2).send_message(OWNER, "oi")
    assert TOKEN not in str(ei.value) and "127.0.0.1" not in str(ei.value) and TOKEN not in caplog.text


def test_httpx_request_log_is_silenced_so_the_url_cannot_leak(server, caplog):
    caplog.set_level(logging.INFO)  # nível comum de produção: o httpx logaria "POST <url com token>"
    tg.TelegramClient(TOKEN, server).send_message(OWNER, "oi")
    assert _Fake.calls and TOKEN not in caplog.text
    assert logging.getLogger("httpx").level == logging.WARNING


def test_exception_text_from_httpx_is_never_forwarded(monkeypatch):
    import httpx

    def boom(url, **kw):
        raise httpx.ConnectError(f"falhou em {url}")  # algumas versões/transportes põem a URL na mensagem

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(tg.TelegramError) as ei:
        tg.TelegramClient(TOKEN).send_message(OWNER, "oi")
    assert TOKEN not in str(ei.value) and "telegram.org" not in str(ei.value)


def test_audit_never_contains_token_or_message_text(db):
    p, a = make_publish_approval(db)
    say(db, OWNER, f"/alterar {a.id} segredo-no-texto"); say(db, STRANGER, "/pendentes segredo-estranho")
    dump = json.dumps([(r.actor, r.action, r.detail) for r in db.scalars(select(AuditLog))], default=str)
    assert TOKEN not in dump and "segredo-no-texto" not in dump and "segredo-estranho" not in dump


# ---------- configuração ----------
def test_bot_refuses_to_run_without_token_or_allowed_users(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(SystemExit, match="TOKEN"):
        tg.run_forever()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN); monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "")
    with pytest.raises(SystemExit, match="ALLOWED"):
        tg.run_forever()


def test_invalid_allowed_ids_fail_loudly(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "abc")
    with pytest.raises(RuntimeError, match="TELEGRAM_ALLOWED_USER_IDS"):
        get_settings()


def test_settings_endpoint_reports_state_without_secrets(client, monkeypatch):
    r = client.get("/settings").json()["integrations"]["telegram"]
    assert "configurado (2" in r and TOKEN not in r
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "")
    assert "ignora todos" in client.get("/settings").json()["integrations"]["telegram"]
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert client.get("/settings").json()["integrations"]["telegram"].startswith("desligado")
