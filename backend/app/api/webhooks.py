"""Webhooks do n8n (Fase 10). Autenticação própria, separada do painel e do X-API-Key.

Escopo mínimo de propósito: o n8n pode ENFILEIRAR tarefa (sem `action`, logo nunca risco), LER o estado das tarefas
que ele mesmo criou, LER o relatório executivo e LER as aprovações pendentes. Não aprova, não rejeita, não executa
a fila e não gasta nada. Segredo compartilhado em cabeçalho: exige HTTPS na produção (guia da Fase 18).
"""
import json
import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes import get_db
from app.core.config import get_settings
from app.models.entities import Approval, Task, WebhookReceipt
from app.schemas import schemas as s
from app.services import ceo
from app.services.tasks import TaskError, audit, create_task

MIN_SECRET_CHARS = 32
MAX_INPUT_CHARS = 20_000
KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,100}$")
RESERVED_INPUT_KEYS = ("handoff",)  # preenchida só pelo sistema (Fase 8); vinda de fora forjaria a cadeia


def require_webhook(x_webhook_secret: str | None = Header(default=None), db: Session = Depends(get_db)) -> None:
    secret = get_settings().n8n_webhook_secret
    if len(secret) < MIN_SECRET_CHARS:  # falha fechado: sem segredo forte configurado, os webhooks não existem
        raise HTTPException(503, f"Webhooks desligados: defina N8N_WEBHOOK_SECRET com {MIN_SECRET_CHARS}+ caracteres")
    if not x_webhook_secret or not secrets.compare_digest(x_webhook_secret, secret):
        audit(db, "n8n", "webhook_denied", {})  # nunca registra o valor recebido
        db.commit()
        raise HTTPException(401, "Segredo de webhook inválido")


router = APIRouter(prefix="/webhooks/n8n", dependencies=[Depends(require_webhook)])


class WebhookTaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # `action` e qualquer campo desconhecido são recusados (422)
    agent_key: str
    description: str = Field(min_length=3, max_length=4000)
    priority: int = Field(default=3, ge=1, le=5)
    input: dict = {}


class WebhookTaskOut(s.TaskOut):
    duplicate: bool = False


@router.post("/tasks", response_model=WebhookTaskOut, status_code=201)
def webhook_create_task(body: WebhookTaskIn, response: Response,
                        idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not idempotency_key or not KEY_RE.match(idempotency_key):
        raise HTTPException(400, "Envie o cabeçalho Idempotency-Key (8 a 100 caracteres: letras, números e . _ : -)")
    if len(json.dumps(body.input, default=str)) > MAX_INPUT_CHARS:
        raise HTTPException(400, f"input acima de {MAX_INPUT_CHARS} caracteres")
    clean_input = {k: v for k, v in body.input.items() if k not in RESERVED_INPUT_KEYS}

    db.add(WebhookReceipt(key=idempotency_key, source="n8n"))
    try:
        db.commit()  # reserva a chave: a restrição única decide a corrida entre dois envios simultâneos
    except IntegrityError:
        db.rollback()
        existing = db.get(WebhookReceipt, idempotency_key)
        if existing is None or existing.task_id is None:
            raise HTTPException(409, "Envio com esta Idempotency-Key ainda em processamento; tente de novo") from None
        response.status_code = 200
        return WebhookTaskOut.model_validate({**s.TaskOut.model_validate(db.get(Task, existing.task_id)).model_dump(),
                                              "duplicate": True})
    try:
        task = create_task(db, body.agent_key, body.description, priority=body.priority, input=clean_input,
                           actor="n8n")
    except TaskError as exc:
        db.rollback()
        db.delete(db.get(WebhookReceipt, idempotency_key))  # falhou: a mesma chave pode ser reenviada corrigida
        db.commit()
        raise HTTPException(400, str(exc)) from exc
    receipt = db.get(WebhookReceipt, idempotency_key)
    receipt.task_id = task.id
    audit(db, "n8n", "webhook_task_created", {"task_id": task.id, "agent": task.agent_key})
    db.commit()
    return WebhookTaskOut.model_validate({**s.TaskOut.model_validate(task).model_dump(), "duplicate": False})


@router.get("/tasks/{task_id}", response_model=s.TaskOut)
def webhook_get_task(task_id: int, db: Session = Depends(get_db)):
    # Só tarefas que chegaram por webhook: o n8n não enxerga o resto do sistema.
    receipt = db.scalar(select(WebhookReceipt).where(WebhookReceipt.task_id == task_id))
    task = db.get(Task, task_id) if receipt else None
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada")
    return task


@router.get("/report")
def webhook_report(db: Session = Depends(get_db)):
    return ceo.executive_report(db)


@router.get("/approvals/pending")
def webhook_pending_approvals(db: Session = Depends(get_db)):
    """Só o necessário para avisar o proprietário; a decisão continua exclusiva do painel."""
    rows = db.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.id)).all()
    return {"count": len(rows), "approvals": [
        {"id": a.id, "task_id": a.task_id, "action": a.action, "consequences": a.consequences,
         "agent": (a.details or {}).get("agent"), "description": str((a.details or {}).get("description", ""))[:200],
         "created_at": a.created_at.isoformat()} for a in rows]}
