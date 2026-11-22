from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_admin
from app.database.session import get_db
from app.models.entities import Agent, Approval, Expense, Experiment, Product, Sale, Task, TaskLog
from app.schemas import schemas as s
from app.services import ceo, costs, experiments, metrics
from app.services.llm import get_provider
from app.services.tasks import TaskError, audit, create_task, decide_approval, run_task

router = APIRouter(dependencies=[Depends(require_admin)])


def _bad(exc: TaskError):
    raise HTTPException(400, str(exc))


# ---- agentes ----
@router.get("/agents", response_model=list[s.AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.scalars(select(Agent).order_by(Agent.key)).all()


@router.post("/agents/{key}/{action}", response_model=s.AgentOut)
def set_agent_status(key: str, action: str, db: Session = Depends(get_db)):
    if action not in ("pause", "activate"):
        raise HTTPException(404, "Ação inválida (use pause ou activate)")
    agent = db.get(Agent, key)
    if agent is None:
        raise HTTPException(404, "Agente não encontrado")
    agent.status = "paused" if action == "pause" else "active"
    audit(db, "admin", f"agent_{action}", {"agent": key})
    db.commit()
    return agent


# ---- tarefas ----
@router.post("/tasks", response_model=s.TaskOut, status_code=201)
def post_task(body: s.TaskCreate, db: Session = Depends(get_db)):
    try:
        return create_task(db, body.agent_key, body.description, priority=body.priority,
                           action=body.action, depends_on=body.depends_on, input=body.input,
                           due_at=body.due_at, actor="admin")
    except TaskError as e:
        _bad(e)


@router.get("/tasks", response_model=list[s.TaskOut])
def list_tasks(status: str | None = None, agent_key: str | None = None,
               db: Session = Depends(get_db)):
    q = select(Task).order_by(Task.id.desc())
    if status:
        q = q.where(Task.status == status)
    if agent_key:
        q = q.where(Task.agent_key == agent_key)
    return db.scalars(q).all()


@router.get("/tasks/{task_id}", response_model=s.TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada")
    return task


@router.get("/tasks/{task_id}/logs", response_model=list[s.TaskLogOut])
def task_logs(task_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(TaskLog).where(TaskLog.task_id == task_id).order_by(TaskLog.id)).all()


@router.post("/tasks/{task_id}/run", response_model=s.TaskOut)
def run_one(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada")
    try:
        return run_task(db, task)
    except TaskError as e:
        _bad(e)


@router.post("/tasks/{task_id}/cancel", response_model=s.TaskOut)
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada")
    if task.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Tarefa já está {task.status}")
    task.status = "cancelled"
    audit(db, "admin", "task_cancelled", {"task_id": task.id})
    db.commit()
    return task


# ---- CEO ----
@router.post("/ceo/plan", response_model=list[s.TaskOut], status_code=201)
def ceo_plan(body: s.GoalIn, db: Session = Depends(get_db)):
    try:
        return ceo.plan_goal(db, body.goal, body.pipeline, body.priority)
    except TaskError as e:
        _bad(e)


@router.post("/ceo/run-next", response_model=s.TaskOut | None)
def ceo_run_next(db: Session = Depends(get_db)):
    return ceo.run_next(db)


@router.post("/ceo/run-all", response_model=list[s.TaskOut])
def ceo_run_all(db: Session = Depends(get_db)):
    return ceo.run_until_blocked(db)


@router.get("/ceo/report")
def ceo_report(db: Session = Depends(get_db)):
    return ceo.executive_report(db)


# ---- aprovações ----
@router.get("/approvals", response_model=list[s.ApprovalOut])
def list_approvals(status: str | None = "pending", db: Session = Depends(get_db)):
    q = select(Approval).order_by(Approval.id.desc())
    if status:
        q = q.where(Approval.status == status)
    return db.scalars(q).all()


@router.post("/approvals/{approval_id}/decide", response_model=s.ApprovalOut)
def decide(approval_id: int, body: s.DecisionIn, db: Session = Depends(get_db)):
    try:
        return decide_approval(db, approval_id, body.decision, body.note)
    except TaskError as e:
        _bad(e)


# ---- produtos ----
@router.post("/products", response_model=s.ProductOut, status_code=201)
def post_product(body: s.ProductIn, db: Session = Depends(get_db)):
    p = Product(**body.model_dump())
    db.add(p)
    audit(db, "admin", "product_created", {"name": body.name})
    db.commit()
    return p


@router.get("/products", response_model=list[s.ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.id)).all()


@router.post("/products/{product_id}/publish", response_model=s.ApprovalOut, status_code=202)
def request_publish(product_id: int, db: Session = Depends(get_db)):
    """Pede aprovação para publicar. O produto só vira 'published' depois de aprovado."""
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "Produto não encontrado")
    if p.status == "published":
        raise HTTPException(400, "Produto já publicado")
    approval = Approval(
        action="publish_commercial_change",
        details={"product_id": p.id, "product": p.name, "price_cents": p.price_cents},
        consequences="Publica o produto para venda ao público.",
    )
    p.status = "in_review"
    db.add(approval)
    audit(db, "admin", "publish_requested", {"product_id": p.id})
    db.commit()
    return approval


# ---- financeiro (registros feitos pelo proprietário; agentes não gastam) ----
@router.post("/sales", status_code=201)
def post_sale(body: s.SaleIn, db: Session = Depends(get_db)):
    if body.fee_cents + body.refunded_cents > body.gross_cents:
        raise HTTPException(400, "Taxas + reembolsos não podem passar do valor bruto")
    sale = Sale(**body.model_dump())
    db.add(sale)
    db.commit()
    return {"id": sale.id}


@router.post("/expenses", status_code=201)
def post_expense(body: s.ExpenseIn, db: Session = Depends(get_db)):
    e = Expense(**body.model_dump())
    db.add(e)
    audit(db, "admin", "expense_recorded", body.model_dump())
    db.commit()
    return {"id": e.id}


# ---- experimentos de validação de oferta (o sistema não gasta: o proprietário registra gasto e vendas) ----
def _experiment(db: Session, experiment_id: int) -> Experiment:
    exp = db.get(Experiment, experiment_id)
    if exp is None:
        raise HTTPException(404, "Experimento não encontrado")
    return exp


def _experiment_out(db: Session, exp: Experiment) -> s.ExperimentOut:
    out = s.ExperimentOut.model_validate(exp)
    out.metrics = experiments.metrics(db, exp)
    return out


@router.post("/experiments", response_model=s.ExperimentOut, status_code=201)
def post_experiment(body: s.ExperimentIn, db: Session = Depends(get_db)):
    if body.product_id is not None and db.get(Product, body.product_id) is None:
        raise HTTPException(404, "Produto não encontrado")
    exp = Experiment(**body.model_dump())
    db.add(exp)
    db.flush()
    audit(db, "admin", "experiment_created", {"experiment_id": exp.id, "budget_cap_cents": exp.budget_cap_cents})
    db.commit()
    return _experiment_out(db, exp)


@router.get("/experiments", response_model=list[s.ExperimentOut])
def list_experiments(db: Session = Depends(get_db)):
    return [_experiment_out(db, e) for e in db.scalars(select(Experiment).order_by(Experiment.id.desc()))]


@router.get("/experiments/{experiment_id}", response_model=s.ExperimentOut)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    return _experiment_out(db, _experiment(db, experiment_id))


@router.post("/experiments/{experiment_id}/request-approval", response_model=s.ApprovalOut, status_code=202)
def request_experiment_approval(experiment_id: int, db: Session = Depends(get_db)):
    """Pede aprovação para o teste começar. Sem aprovação o experimento não autoriza nenhum gasto."""
    exp = _experiment(db, experiment_id)
    if exp.status != "draft":
        raise HTTPException(409, f"Só um rascunho pede aprovação (status atual: {exp.status})")
    details, consequences = experiments.request_approval_details(exp)
    approval = Approval(action="activate_campaign", details=details, consequences=consequences)
    exp.status = "pending_approval"
    db.add(approval)
    audit(db, "admin", "experiment_approval_requested", {"experiment_id": exp.id})
    db.commit()
    return approval


@router.post("/experiments/{experiment_id}/spend", status_code=201)
def post_experiment_spend(experiment_id: int, body: s.ExperimentSpendIn, db: Session = Depends(get_db)):
    exp = _experiment(db, experiment_id)
    if exp.status == "closed":
        raise HTTPException(409, "Experimento encerrado: não aceita novos registros")
    e = Expense(category="ads", description=body.note or f"Experimento #{exp.id}: {exp.name}",
                amount_cents=body.amount_cents, experiment_id=exp.id)
    db.add(e)
    audit(db, "admin", "experiment_spend_recorded", {"experiment_id": exp.id, "amount_cents": body.amount_cents})
    db.commit()
    return {"id": e.id, "metrics": experiments.metrics(db, exp)}


@router.post("/experiments/{experiment_id}/sales", status_code=201)
def post_experiment_sale(experiment_id: int, body: s.ExperimentSaleIn, db: Session = Depends(get_db)):
    exp = _experiment(db, experiment_id)
    if exp.status == "closed":
        raise HTTPException(409, "Experimento encerrado: não aceita novos registros")
    if body.fee_cents + body.refunded_cents > body.gross_cents:
        raise HTTPException(400, "Taxas + reembolsos não podem passar do valor bruto")
    sale = Sale(product_id=exp.product_id, experiment_id=exp.id, **body.model_dump())
    db.add(sale)
    db.commit()
    return {"id": sale.id, "metrics": experiments.metrics(db, exp)}


@router.post("/experiments/{experiment_id}/close", response_model=s.ExperimentOut)
def close_experiment(experiment_id: int, body: s.ExperimentCloseIn, db: Session = Depends(get_db)):
    exp = _experiment(db, experiment_id)
    try:
        experiments.close(db, exp, body.outcome, body.note)
    except experiments.ExperimentError as e:
        raise HTTPException(409, str(e))
    audit(db, "admin", "experiment_closed", {"experiment_id": exp.id, "outcome": body.outcome})
    db.commit()
    return _experiment_out(db, exp)


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    return metrics.dashboard(db)


@router.get("/dashboard/series")
def get_series(days: int = 30, db: Session = Depends(get_db)):
    return metrics.series(db, days)


@router.get("/agents-stats")
def agents_stats(db: Session = Depends(get_db)):
    return metrics.agent_stats(db)


# ---- custos de IA, provedores e configuração (somente leitura) ----
@router.get("/costs")
def get_costs(db: Session = Depends(get_db)):
    return costs.summary(db)


@router.get("/providers/status")
def provider_status():
    """Verifica o provedor de IA configurado agora. Não consome tokens."""
    try:
        provider = get_provider()
    except ValueError as exc:
        return {"provider": get_settings().llm_provider, "ok": False, "detail": str(exc), "model": ""}
    ok, detail = provider.check()
    return {"provider": provider.name, "model": provider.model, "ok": ok, "detail": detail,
            "paid": provider.paid}


@router.get("/settings")
def get_app_settings():
    """Configuração atual, sem segredos. Para alterar, edite as variáveis de ambiente e reinicie."""
    st = get_settings()
    return {
        "llm_provider": st.llm_provider,
        "ollama_url": st.ollama_url,
        "ollama_model": st.ollama_model,
        "max_task_attempts": st.max_task_attempts,
        "ai_monthly_budget_usd": st.ai_monthly_budget_usd,
        "database_dialect": st.database_url.split(":", 1)[0].split("+", 1)[0],
        "admin_key_configured": bool(st.admin_api_key),
        "owner_account_configured": bool(st.owner_email and st.owner_password),
        "integrations": {
            "telegram": "não implementado",
            "n8n": "workflow de mineração pronto para importar; webhooks do backend não implementados",
            "claude": "não implementado",
            "gemini": "não implementado",
        },
    }
