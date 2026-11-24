"""Comunicação entre agentes (Fase 8): mensagens e handoffs registrados, auditáveis e sem loops.

- Mensagem: registro entre dois agentes (não executa nada).
- Handoff: o agente de origem passa trabalho a outro; cria uma tarefa normal para o destino, vinculada à tarefa
  de origem (que precisa estar concluída e ser do agente que passa o trabalho).
Travas contra loop: nunca para si mesmo; nunca para um agente que já está no caminho da cadeia (impede A->B->A);
profundidade máxima MAX_HANDOFF_DEPTH. A cadeia fica na própria tarefa em `input["handoff"]`, que o sistema
sobrescreve (quem chama não consegue forjar caminho nem profundidade). Handoff nunca define `action`:
risco continua decidido pela política só quando a tarefa recebe uma ação, e handoff não concede nenhuma.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Agent, AgentMessage, Task, TaskStatus
from app.services.tasks import TaskError, add_log, audit, create_task

MAX_HANDOFF_DEPTH = 5  # heurística nossa: cadeias mais longas costumam indicar loop ou plano mal desenhado
MAX_BODY_CHARS = 4000
MAX_SUBJECT_CHARS = 150


def _check_agents(db: Session, from_agent: str, to_agent: str) -> None:
    for key in (from_agent, to_agent):
        if db.get(Agent, key) is None:
            raise TaskError(f"Agente desconhecido: {key}")
    if from_agent == to_agent:
        raise TaskError("Um agente não pode enviar mensagem ou handoff para si mesmo")


def _check_text(subject: str, body: str) -> None:
    if not subject.strip():
        raise TaskError("Informe o assunto")
    if len(subject) > MAX_SUBJECT_CHARS or len(body) > MAX_BODY_CHARS:
        raise TaskError(f"Assunto até {MAX_SUBJECT_CHARS} e corpo até {MAX_BODY_CHARS} caracteres")


def send_message(db: Session, from_agent: str, to_agent: str, subject: str, body: str = "", *,
                 task_id: int | None = None, parent_id: int | None = None, actor: str = "admin") -> AgentMessage:
    _check_agents(db, from_agent, to_agent)
    _check_text(subject, body)
    if task_id is not None and db.get(Task, task_id) is None:
        raise TaskError(f"Tarefa inexistente: {task_id}")
    hop = 0
    if parent_id is not None:
        parent = db.get(AgentMessage, parent_id)
        if parent is None:
            raise TaskError(f"Mensagem inexistente: {parent_id}")
        hop = parent.hop + 1
        if hop > MAX_HANDOFF_DEPTH:
            raise TaskError(f"Cadeia de respostas acima do limite ({MAX_HANDOFF_DEPTH})")
    msg = AgentMessage(kind="message", from_agent=from_agent, to_agent=to_agent, subject=subject.strip(),
                       body=body, task_id=task_id, parent_id=parent_id, hop=hop)
    db.add(msg)
    db.flush()
    audit(db, actor, "agent_message", {"message_id": msg.id, "from": from_agent, "to": to_agent, "task_id": task_id})
    db.commit()
    return msg


def handoff(db: Session, from_task_id: int, to_agent: str, description: str, *, subject: str = "",
            input: dict | None = None, priority: int = 3, actor: str = "admin") -> AgentMessage:
    origin = db.get(Task, from_task_id)
    if origin is None:
        raise TaskError(f"Tarefa de origem inexistente: {from_task_id}")
    if origin.status != TaskStatus.COMPLETED:
        raise TaskError("Só tarefas concluídas podem passar trabalho adiante")
    from_agent = origin.agent_key
    _check_agents(db, from_agent, to_agent)
    subject = subject.strip() or description.strip()[:MAX_SUBJECT_CHARS]
    _check_text(subject, description)
    chain = (origin.input or {}).get("handoff") or {}
    path = list(chain.get("path") or [from_agent])
    hop = int(chain.get("hop", 0)) + 1
    if to_agent in path:
        raise TaskError(f"Loop bloqueado: {to_agent} já participou desta cadeia ({' -> '.join(path)})")
    if hop > MAX_HANDOFF_DEPTH:
        raise TaskError(f"Profundidade máxima de handoff ({MAX_HANDOFF_DEPTH}) atingida")
    new_input = {**(input or {}), "handoff": {"from_agent": from_agent, "from_task_id": origin.id,
                                              "hop": hop, "path": path + [to_agent]}}
    task = create_task(db, to_agent, description, priority=priority, depends_on=[origin.id],
                       input=new_input, actor=actor)
    msg = AgentMessage(kind="handoff", from_agent=from_agent, to_agent=to_agent, subject=subject, body=description,
                       task_id=origin.id, handoff_task_id=task.id, hop=hop)
    db.add(msg)
    db.flush()
    add_log(db, origin, "handoff_sent", f"para {to_agent}: tarefa {task.id}")
    add_log(db, task, "handoff_received", f"de {from_agent}: tarefa {origin.id}")
    audit(db, actor, "agent_handoff", {"message_id": msg.id, "from": from_agent, "to": to_agent,
                                       "from_task_id": origin.id, "new_task_id": task.id, "hop": hop})
    db.commit()
    return msg


def list_messages(db: Session, *, agent: str | None = None, task_id: int | None = None,
                  kind: str | None = None, limit: int = 100) -> list[AgentMessage]:
    q = select(AgentMessage).order_by(AgentMessage.id.desc()).limit(max(1, min(limit, 500)))
    if agent:
        q = q.where((AgentMessage.from_agent == agent) | (AgentMessage.to_agent == agent))
    if task_id is not None:
        q = q.where((AgentMessage.task_id == task_id) | (AgentMessage.handoff_task_id == task_id))
    if kind:
        q = q.where(AgentMessage.kind == kind)
    return list(db.scalars(q).all())
