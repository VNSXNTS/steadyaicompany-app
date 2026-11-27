"""Bot do Telegram (Fase 12): avisos de aprovação pendente e decisão pelo celular.

Regras de segurança (todas cobertas por testes):
- Falha fechada: sem TELEGRAM_BOT_TOKEN o bot não roda; sem TELEGRAM_ALLOWED_USER_IDS ele ignora todo mundo.
- Só conversa privada com um usuário autorizado. Qualquer outra pessoa só recebe o próprio ID em `/id`.
- APROVAR exige duas etapas (código de 4 dígitos, uso único, 2 minutos, preso ao usuário, à aprovação e à decisão).
  Rejeitar e pedir alterações são imediatos: não executam nada de risco.
- Aprovar passa pelo mesmo `decide_approval` do painel, com as mesmas travas (inclusive a dos experimentos).
- O token nunca aparece em log, erro, auditoria ou resposta. A URL da API do Telegram carrega o token, então os
  erros são reescritos sem URL e o logger do httpx é silenciado.
- Sem Markdown/HTML nas mensagens (texto puro), para não interpretar conteúdo de tarefa como formatação.
"""
import logging
import secrets
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Approval, AuditLog
from app.services.tasks import TaskError, audit, decide_approval

logger = logging.getLogger("steady.telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)  # o httpx loga a URL, e a URL tem o token
logging.getLogger("httpcore").setLevel(logging.WARNING)

CONFIRM_TTL_SECONDS = 120
MAX_TEXT = 3500
_confirmations: dict[tuple[int, int], tuple[str, float]] = {}  # (user_id, approval_id) -> (código, expira)


class TelegramError(Exception):
    """Erro da API do Telegram, sempre sem URL nem token."""


class TelegramClient:
    def __init__(self, token: str, base: str = "https://api.telegram.org", timeout: float = 40.0):
        self._token, self._base, self._timeout = token, base.rstrip("/"), timeout

    def _call(self, method: str, payload: dict) -> dict:
        try:
            r = httpx.post(f"{self._base}/bot{self._token}/{method}", json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise TelegramError(f"{method}: falha de rede ({type(exc).__name__})") from None
        if r.status_code != 200:
            raise TelegramError(f"{method}: HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise TelegramError(f"{method}: resposta inválida") from None
        if not data.get("ok"):
            raise TelegramError(f"{method}: recusado pelo Telegram")
        return data

    def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        payload: dict = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload).get("result", [])

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text[:MAX_TEXT], "disable_web_page_preview": True})


# ---- comandos ----
HELP = (
    "Comandos:\n"
    "/pendentes: lista as aprovações pendentes\n"
    "/ver N: mostra o que será autorizado\n"
    "/aprovar N: pede a aprovação (você confirma com um código)\n"
    "/confirmar N CODIGO: conclui a aprovação\n"
    "/rejeitar N: rejeita\n"
    "/alterar N motivo: pede alterações\n"
    "/id: mostra o seu ID do Telegram"
)


def _describe(a: Approval) -> str:
    when = a.created_at.strftime("%d/%m %H:%M") if a.created_at else ""
    return f"#{a.id} [{a.action}] {when}\n{a.consequences or 'Sem descrição de consequências.'}"


def _arg_id(parts: list[str]) -> int | None:
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None


def _decide(db: Session, user_id: int, approval_id: int, decision: str, note: str) -> str:
    try:
        decide_approval(db, approval_id, decision, note)
    except TaskError as e:
        audit(db, f"telegram:{user_id}", "telegram_decision_failed", {"approval_id": approval_id, "decision": decision})
        db.commit()
        return f"Não foi possível: {e}"
    audit(db, f"telegram:{user_id}", "telegram_decision", {"approval_id": approval_id, "decision": decision})
    db.commit()
    label = {"approved": "APROVADA", "rejected": "REJEITADA", "changes_requested": "alterações pedidas"}[decision]
    return f"Aprovação #{approval_id}: {label}."


def handle_command(db: Session, user_id: int, text: str, *, now: float | None = None) -> str:
    """Resposta a UM comando de um usuário JÁ autorizado."""
    now = time.monotonic() if now is None else now
    parts = text.strip().split(maxsplit=2)
    cmd = parts[0].lower().split("@", 1)[0] if parts else ""
    if cmd in ("/start", "/ajuda", "/help"):
        return HELP
    if cmd == "/id":
        return f"Seu ID: {user_id}"
    if cmd == "/pendentes":
        rows = db.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.id)).all()
        if not rows:
            return "Nenhuma aprovação pendente."
        return "Pendentes:\n\n" + "\n\n".join(_describe(a) for a in rows[:10]) + (f"\n\n(+{len(rows) - 10} no painel)" if len(rows) > 10 else "")
    n = _arg_id(parts)
    if cmd in ("/ver", "/aprovar", "/rejeitar", "/alterar", "/confirmar") and n is None:
        return f"Informe o número da aprovação. Exemplo: {cmd} 12"
    a = db.get(Approval, n) if n is not None else None
    if cmd in ("/ver", "/aprovar", "/rejeitar", "/alterar", "/confirmar") and a is None:
        return f"Aprovação #{n} não encontrada."
    if cmd == "/ver":
        return _describe(a) + f"\nEstado: {a.status}"
    if cmd == "/aprovar":
        if a.status != "pending":
            return f"Aprovação #{n} já está: {a.status}."
        code = f"{secrets.randbelow(10000):04d}"
        _confirmations[(user_id, n)] = (code, now + CONFIRM_TTL_SECONDS)
        audit(db, f"telegram:{user_id}", "telegram_confirm_requested", {"approval_id": n})
        db.commit()
        return f"{_describe(a)}\n\nPara APROVAR, envie em até 2 minutos:\n/confirmar {n} {code}"
    if cmd == "/confirmar":
        given = parts[2].strip() if len(parts) > 2 else ""
        stored = _confirmations.pop((user_id, n), None)  # uso único: some mesmo se o código estiver errado
        if stored is None or now > stored[1]:
            return "Sem pedido de aprovação válido (ou expirou). Envie /aprovar de novo."
        if not secrets.compare_digest(stored[0], given):
            return "Código errado. Envie /aprovar de novo para gerar outro."
        return _decide(db, user_id, n, "approved", "Aprovado pelo Telegram")
    if cmd == "/rejeitar":
        return _decide(db, user_id, n, "rejected", "Rejeitado pelo Telegram")
    if cmd == "/alterar":
        note = parts[2].strip()[:500] if len(parts) > 2 else ""
        if not note:
            return "Diga o que mudar. Exemplo: /alterar 12 baixar o orçamento"
        return _decide(db, user_id, n, "changes_requested", note)
    return "Não entendi. Envie /ajuda."


def handle_update(db: Session, client, update: dict) -> None:
    """Processa uma atualização do Telegram. Nunca lança erro por conteúdo malformado."""
    msg = update.get("message") if isinstance(update, dict) else None
    if not isinstance(msg, dict):
        return
    sender, chat, text = msg.get("from"), msg.get("chat"), msg.get("text")
    if not (isinstance(sender, dict) and isinstance(chat, dict) and isinstance(text, str) and isinstance(sender.get("id"), int)):
        return
    user_id, chat_id = sender["id"], chat.get("id")
    if sender.get("is_bot") or chat.get("type") != "private" or chat_id != user_id:
        return  # grupos, canais e bots nunca são atendidos
    allowed = get_settings().telegram_allowed_user_ids
    if user_id not in allowed:
        audit(db, f"telegram:{user_id}", "telegram_denied", {})
        db.commit()
        if text.strip().lower().split("@", 1)[0] == "/id":
            client.send_message(chat_id, f"Seu ID: {user_id}. Coloque em TELEGRAM_ALLOWED_USER_IDS para autorizar.")
        return
    client.send_message(chat_id, handle_command(db, user_id, text))


# ---- avisos ----
def notify_pending(db: Session, client) -> int:
    """Avisa cada usuário autorizado de cada aprovação pendente, uma vez só. Devolve quantas aprovações avisou."""
    allowed = get_settings().telegram_allowed_user_ids
    if not allowed:
        return 0
    done = {d.get("approval_id") for (d,) in db.execute(select(AuditLog.detail).where(AuditLog.action == "telegram_notified"))}
    sent = 0
    for a in db.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.id)).all():
        if a.id in done:
            continue
        try:
            for uid in allowed:
                client.send_message(uid, f"Aprovação pendente\n{_describe(a)}\n\nResponda /aprovar {a.id}, /rejeitar {a.id} ou /ver {a.id}.")
        except TelegramError as exc:
            logger.warning("aviso não enviado: %s", exc)
            return sent  # tenta de novo no próximo ciclo; nada é marcado como avisado
        audit(db, "telegram", "telegram_notified", {"approval_id": a.id})
        db.commit()
        sent += 1
    return sent


def run_forever(poll_seconds: int = 25) -> None:  # pragma: no cover - laço de rede
    from app.database.session import SessionLocal

    st = get_settings()
    if not st.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN não configurado: bot desligado.")
    if not st.telegram_allowed_user_ids:
        raise SystemExit("TELEGRAM_ALLOWED_USER_IDS vazio: o bot ignoraria todo mundo. Configure seu ID (mande /id ao bot).")
    client = TelegramClient(st.telegram_bot_token, st.telegram_api_base, timeout=poll_seconds + 15)
    offset, backoff = None, 1
    print(f"Bot do Telegram rodando para {len(st.telegram_allowed_user_ids)} usuário(s). Ctrl+C para parar.")
    while True:
        try:
            with SessionLocal() as db:
                notify_pending(db, client)
                for upd in client.get_updates(offset, poll_seconds):
                    offset = upd["update_id"] + 1
                    handle_update(db, client, upd)
            backoff = 1
        except TelegramError as exc:  # modo reduzido: o resto do sistema segue sem o bot
            logger.warning("telegram indisponível: %s", exc)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except KeyboardInterrupt:
            return


if __name__ == "__main__":  # pragma: no cover
    run_forever()
