"""Números do dashboard. Tudo vem do banco; sem dados, os valores são zero (nunca fictícios).

Valores em centavos. Lucro = receita líquida - despesas.
Receita líquida = bruto - taxas - reembolsos. Faturamento NÃO é lucro.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Agent, Expense, Product, Sale, Task, TaskLog, TaskStatus


def dashboard(db: Session) -> dict:
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    gross, fees, refunds = db.execute(
        select(func.coalesce(func.sum(Sale.gross_cents), 0),
               func.coalesce(func.sum(Sale.fee_cents), 0),
               func.coalesce(func.sum(Sale.refunded_cents), 0))
    ).one()
    expenses = db.scalar(select(func.coalesce(func.sum(Expense.amount_cents), 0))) or 0
    net_revenue = gross - fees - refunds
    profit = net_revenue - expenses
    margin = round(profit / net_revenue * 100, 2) if net_revenue > 0 else None
    roi = round(profit / expenses * 100, 2) if expenses > 0 else None

    recent = db.scalars(select(TaskLog).order_by(TaskLog.id.desc()).limit(10)).all()
    return {
        "agents_active": count(Agent, Agent.status == "active"),
        "agents_total": count(Agent),
        "tasks_running": count(Task, Task.status == TaskStatus.RUNNING),
        "tasks_pending": count(Task, Task.status == TaskStatus.PENDING),
        "approvals_needed": count(Task, Task.status == TaskStatus.AWAITING_APPROVAL),
        "products_developed": count(Product),
        "products_published": count(Product, Product.status == "published"),
        "sales_count": count(Sale),
        "gross_revenue_cents": gross,
        "fees_cents": fees,
        "refunds_cents": refunds,
        "net_revenue_cents": net_revenue,
        "expenses_cents": expenses,
        "profit_cents": profit,
        "margin_percent": margin,  # None quando não há receita líquida
        "roi_percent": roi,        # None quando não há despesas
        "recent_activity": [
            {"task_id": r.task_id, "event": r.event, "message": r.message,
             "at": r.created_at.isoformat()} for r in recent
        ],
    }


def series(db: Session, days: int = 30) -> dict:
    """Série diária (últimos N dias) vinda do banco: receita líquida, despesas e tarefas concluídas.

    Sem dados, todos os pontos são zero. Valores em centavos.
    """
    from datetime import datetime, timedelta, timezone

    days = max(1, min(days, 365))
    today = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)
    buckets = {start_day + timedelta(days=i): {"net_revenue_cents": 0, "expenses_cents": 0, "tasks_completed": 0}
               for i in range(days)}

    for s in db.scalars(select(Sale).where(Sale.created_at >= start)):
        d = s.created_at.date()
        if d in buckets:
            buckets[d]["net_revenue_cents"] += s.gross_cents - s.fee_cents - s.refunded_cents
    for e in db.scalars(select(Expense).where(Expense.created_at >= start)):
        d = e.created_at.date()
        if d in buckets:
            buckets[d]["expenses_cents"] += e.amount_cents
    for log in db.scalars(select(TaskLog).where(TaskLog.created_at >= start, TaskLog.event == "completed")):
        d = log.created_at.date()
        if d in buckets:
            buckets[d]["tasks_completed"] += 1

    return {"days": [{"date": d.isoformat(), **v} for d, v in sorted(buckets.items())]}


def agent_stats(db: Session) -> list[dict]:
    """Tarefas por agente e status, para a central de agentes."""
    rows = db.execute(select(Task.agent_key, Task.status, func.count()).group_by(Task.agent_key, Task.status)).all()
    out: dict[str, dict] = {}
    for key, status, n in rows:
        out.setdefault(key, {"agent_key": key, **{s: 0 for s in TaskStatus.ALL}})[status] = n
    for a in db.scalars(select(Agent)):
        out.setdefault(a.key, {"agent_key": a.key, **{s: 0 for s in TaskStatus.ALL}})
    return sorted(out.values(), key=lambda r: r["agent_key"])
