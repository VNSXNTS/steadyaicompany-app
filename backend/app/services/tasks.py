"""Fila de tarefas: criação, execução com tentativas, aprovações e histórico."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Agent, Approval, AuditLog, Experiment, Product, Task, TaskLog, TaskStatus
from app.services import costs, experiments, policy
from app.services.llm import LLMProvider, get_provider

logger = logging.getLogger("steady.tasks")


class TaskError(Exception):
    pass


def add_log(db: Session, task: Task, event: str, message: str = "") -> None:
    db.add(TaskLog(task_id=task.id, event=event, message=message))


def audit(db: Session, actor: str, action: str, detail: dict | None = None) -> None:
    db.add(AuditLog(actor=actor, action=action, detail=detail or {}))


def create_task(
    db: Session,
    agent_key: str,
    description: str,
    *,
    priority: int = 3,
    action: str | None = None,
    depends_on: list[int] | None = None,
    input: dict | None = None,
    due_at: datetime | None = None,
    actor: str = "system",
) -> Task:
    agent = db.get(Agent, agent_key)
    if agent is None:
        raise TaskError(f"Agente desconhecido: {agent_key}")
    if not 1 <= priority <= 5:
        raise TaskError("priority deve estar entre 1 (mais alta) e 5")
    depends_on = depends_on or []
    for dep_id in depends_on:
        if db.get(Task, dep_id) is None:
            raise TaskError(f"Dependência inexistente: tarefa {dep_id}")

    # A aprovação é decidida pela política, nunca por quem cria a tarefa.
    needs_approval = policy.is_risky(action)
    task = Task(
        agent_key=agent_key,
        department=agent.department,
        description=description,
        priority=priority,
        action=action,
        requires_approval=needs_approval,
        depends_on=depends_on,
        input=input or {},
        due_at=due_at,
        status=TaskStatus.AWAITING_APPROVAL if needs_approval else TaskStatus.PENDING,
    )
    db.add(task)
    db.flush()
    add_log(db, task, "created", f"por {actor}")
    if needs_approval:
        db.add(Approval(
            task_id=task.id, action=action,
            details={"agent": agent_key, "description": description, **(input or {})},
            consequences=policy.consequences_for(action),
        ))
        add_log(db, task, "awaiting_approval", policy.consequences_for(action))
    audit(db, actor, "task_created", {"task_id": task.id, "agent": agent_key, "action": action})
    db.commit()
    return task


def _deps_done(db: Session, task: Task) -> bool:
    if not task.depends_on:
        return True
    done = db.scalars(
        select(Task.id).where(Task.id.in_(task.depends_on), Task.status == TaskStatus.COMPLETED)
    ).all()
    return len(done) == len(set(task.depends_on))


def next_runnable(db: Session) -> Task | None:
    candidates = db.scalars(
        select(Task).where(Task.status == TaskStatus.PENDING).order_by(Task.priority, Task.id)
    ).all()
    for t in candidates:
        agent = db.get(Agent, t.agent_key)
        if agent and agent.status == "active" and _deps_done(db, t):
            return t
    return None


def run_task(db: Session, task: Task, provider: LLMProvider | None = None) -> Task:
    if task.status != TaskStatus.PENDING:
        raise TaskError(f"Só tarefas pendentes podem rodar (status atual: {task.status})")
    agent = db.get(Agent, task.agent_key)
    if agent.status != "active":
        raise TaskError(f"O agente {agent.key} está pausado")
    if not _deps_done(db, task):
        raise TaskError("Dependências ainda não concluídas")

    provider = provider or get_provider()

    # Nenhum provedor pago roda sem orçamento autorizado (AI_MONTHLY_BUDGET_USD) ou acima dele.
    # A tarefa continua pendente: nada é consumido e nada fica marcado como feito.
    if provider.paid and costs.month_spend_micro_usd(db) >= costs.budget_micro_usd():
        raise TaskError(
            f"Provedor pago '{provider.name}' bloqueado: orçamento mensal de IA não autorizado ou esgotado"
        )

    max_attempts = get_settings().max_task_attempts
    task.status = TaskStatus.RUNNING
    task.attempts += 1
    add_log(db, task, "started", f"tentativa {task.attempts}/{max_attempts}")
    db.commit()
    try:
        result = provider.complete(system=f"{agent.name}: {agent.role}", prompt=task.description)
        task.output = {"text": result.text, "provider": provider.name, "model": provider.model,
                       "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens}
        task.error = None
        task.status = TaskStatus.COMPLETED
        costs.record_usage(db, task_id=task.id, provider=provider.name, model=provider.model,
                           prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
                           cost_micro_usd=provider.cost_micro_usd(result.prompt_tokens, result.completion_tokens),
                           ok=True)
        add_log(db, task, "completed")
    except Exception as exc:  # falha do provedor: tenta de novo até o limite
        task.error = f"{type(exc).__name__}: {exc}"
        costs.record_usage(db, task_id=task.id, provider=provider.name, model=provider.model,
                           prompt_tokens=0, completion_tokens=0, cost_micro_usd=0, ok=False)
        logger.warning("falha do provedor de IA", extra={"task_id": task.id, "provider": provider.name})
        if task.attempts >= max_attempts:
            task.status = TaskStatus.FAILED
            add_log(db, task, "failed", task.error)
        else:
            task.status = TaskStatus.PENDING
            add_log(db, task, "retry_scheduled", task.error)
    agent.last_run_at = datetime.now(timezone.utc)
    db.commit()
    return task


def decide_approval(db: Session, approval_id: int, decision: str, note: str = "") -> Approval:
    if decision not in ("approved", "rejected", "changes_requested"):
        raise TaskError("decision deve ser approved, rejected ou changes_requested")
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise TaskError("Aprovação não encontrada")
    if approval.status != "pending":
        raise TaskError(f"Aprovação já decidida: {approval.status}")

    # Aprovar um experimento revalida o plano e a recomendação com os dados de AGORA (Fase 16b, M1).
    # Rejeitar ou pedir alterações nunca é bloqueado. Bloqueado: a aprovação continua pendente.
    gate_id = approval.details.get("experiment_id") if approval.action == "activate_campaign" else None
    gate_exp = db.get(Experiment, gate_id) if gate_id else None
    if decision == "approved" and gate_exp is not None and gate_exp.status == "pending_approval":
        blockers = experiments.approval_blockers(db, gate_exp)
        if blockers:
            audit(db, "admin", "experiment_approval_blocked",
                  {"approval_id": approval.id, "experiment_id": gate_exp.id, "reasons": blockers})
            db.commit()
            raise TaskError("Aprovação bloqueada: " + " | ".join(blockers))
        audit(db, "admin", "experiment_approval_revalidated", {"approval_id": approval.id, "experiment_id": gate_exp.id})

    approval.status = decision
    approval.decision_note = note
    approval.decided_at = datetime.now(timezone.utc)

    task = db.get(Task, approval.task_id) if approval.task_id else None
    if task is not None:
        if decision == "approved":
            task.status = TaskStatus.PENDING  # agora pode entrar na fila
            add_log(db, task, "approved", note)
        else:
            task.status = TaskStatus.CANCELLED
            add_log(db, task, decision, note)

    # Publicar um produto só acontece com aprovação.
    if decision == "approved" and approval.action == "publish_commercial_change":
        pid = approval.details.get("product_id")
        product = db.get(Product, pid) if pid else None
        if product is not None:
            product.status = "published"

    # Um experimento só passa a valer (autoriza gasto) com aprovação. Pedir alterações volta a rascunho.
    exp_id = approval.details.get("experiment_id") if approval.action == "activate_campaign" else None
    experiment = db.get(Experiment, exp_id) if exp_id else None
    if experiment is not None and experiment.status == "pending_approval":
        if decision == "approved":
            experiment.status = "approved"
            experiment.approved_at = datetime.now(timezone.utc)
        elif decision == "rejected":
            experiment.status = "rejected"
        else:
            experiment.status = "draft"

    audit(db, "admin", f"approval_{decision}", {"approval_id": approval.id, "action": approval.action})
    db.commit()
    return approval
