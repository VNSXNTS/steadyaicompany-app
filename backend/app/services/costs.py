"""Registro e monitoramento de custos de IA. Valores em milionésimos de dólar (micro-USD)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AIUsage, Expense

MICRO = 1_000_000


def month_start() -> datetime:
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def record_usage(db: Session, *, task_id: int | None, provider: str, model: str,
                 prompt_tokens: int, completion_tokens: int, cost_micro_usd: int, ok: bool) -> None:
    db.add(AIUsage(task_id=task_id, provider=provider, model=model, prompt_tokens=prompt_tokens,
                   completion_tokens=completion_tokens, cost_micro_usd=cost_micro_usd, ok=ok))


def month_spend_micro_usd(db: Session) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(AIUsage.cost_micro_usd), 0)).where(AIUsage.created_at >= month_start())
    ) or 0


def budget_micro_usd() -> int:
    return int(round(get_settings().ai_monthly_budget_usd * MICRO))


def summary(db: Session) -> dict:
    start = month_start()
    rows = db.execute(
        select(AIUsage.provider, func.count(), func.coalesce(func.sum(AIUsage.prompt_tokens), 0),
               func.coalesce(func.sum(AIUsage.completion_tokens), 0),
               func.coalesce(func.sum(AIUsage.cost_micro_usd), 0))
        .where(AIUsage.created_at >= start).group_by(AIUsage.provider)
    ).all()
    failed = db.scalar(select(func.count()).select_from(AIUsage)
                       .where(AIUsage.created_at >= start, AIUsage.ok.is_(False))) or 0
    spend = sum(r[4] for r in rows)
    budget = budget_micro_usd()
    ai_expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(Expense.category == "ai")) or 0
    by_model = db.execute(
        select(AIUsage.provider, AIUsage.model, func.count(), func.coalesce(func.sum(AIUsage.cost_micro_usd), 0))
        .where(AIUsage.created_at >= start).group_by(AIUsage.provider, AIUsage.model)
        .order_by(func.sum(AIUsage.cost_micro_usd).desc())
    ).all()
    since = datetime.now(timezone.utc) - timedelta(days=29)
    day = func.date(AIUsage.created_at)
    daily = db.execute(
        select(day, func.count(), func.coalesce(func.sum(AIUsage.cost_micro_usd), 0))
        .where(AIUsage.created_at >= since.replace(hour=0, minute=0, second=0, microsecond=0))
        .group_by(day).order_by(day)
    ).all()
    return {
        "month_start": start.isoformat(),
        "calls": sum(r[1] for r in rows),
        "failed_calls": failed,
        "prompt_tokens": sum(r[2] for r in rows),
        "completion_tokens": sum(r[3] for r in rows),
        "spend_usd": round(spend / MICRO, 6),
        "budget_usd": round(budget / MICRO, 2),
        "budget_used_percent": round(spend / budget * 100, 2) if budget > 0 else None,
        "paid_providers_allowed": budget > 0,
        "remaining_usd": round(max(budget - spend, 0) / MICRO, 6) if budget > 0 else None,
        "by_model": [{"provider": r[0], "model": r[1], "calls": r[2], "spend_usd": round(r[3] / MICRO, 6)}
                     for r in by_model],
        "daily": [{"date": str(r[0]), "calls": r[1], "spend_usd": round(r[2] / MICRO, 6)} for r in daily],
        "by_provider": [
            {"provider": r[0], "calls": r[1], "prompt_tokens": r[2], "completion_tokens": r[3],
             "spend_usd": round(r[4] / MICRO, 6)} for r in rows
        ],
        # despesas de IA lançadas manualmente pelo proprietário (ex.: assinatura de API)
        "manual_ai_expenses_cents": ai_expenses,
    }
