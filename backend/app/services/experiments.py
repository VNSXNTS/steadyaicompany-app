"""Experimentos de validação de oferta: métricas e recomendação por regras.

Princípios (do método de validar com pouco orçamento, e das regras do projeto):
- Teto de gasto e critérios de parada são definidos ANTES de gastar e não podem ser editados.
- O sistema RECOMENDA; quem decide encerrar ou validar é o proprietário.
- Só se pode marcar "validada" uma oferta que cumpriu as regras de evidência e de CPA.
- Dinheiro em centavos. ROI e CPA são `None` quando não há base (nunca 0 inventado).
- Receita líquida = bruto - taxas - reembolsos. Lucro = líquida - despesas do experimento.
- Uma recomendação NÃO é garantia de lucro: poucas vendas são evidência fraca.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Expense, Experiment, Sale
from app.services import policy


class ExperimentError(Exception):
    pass


def unit_fee_cents(exp: Experiment) -> int:
    return exp.price_cents * exp.fee_bps // 10_000 + exp.fee_fixed_cents


def break_even_cpa_cents(exp: Experiment) -> int:
    """Quanto se pode pagar por venda sem prejuízo: preço - taxas da plataforma (reembolsos não estimados)."""
    return max(exp.price_cents - unit_fee_cents(exp), 0)


def _totals(db: Session, exp: Experiment) -> dict:
    spend = db.scalar(select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(Expense.experiment_id == exp.id))
    row = db.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.gross_cents), 0),
            func.coalesce(func.sum(Sale.fee_cents), 0),
            func.coalesce(func.sum(Sale.refunded_cents), 0),
        ).where(Sale.experiment_id == exp.id)
    ).one()
    return {"spend": int(spend), "sales": int(row[0]), "gross": int(row[1]), "fees": int(row[2]), "refunded": int(row[3])}


def metrics(db: Session, exp: Experiment) -> dict:
    t = _totals(db, exp)
    net = t["gross"] - t["fees"] - t["refunded"]
    profit = net - t["spend"]
    cpa = round(t["spend"] / t["sales"]) if t["sales"] > 0 else None
    be = break_even_cpa_cents(exp)
    warnings: list[str] = []
    if be == 0:
        warnings.append("Taxas igualam ou superam o preço: nenhuma venda dá lucro com esses parâmetros.")
    if t["spend"] > 0 and exp.status not in ("approved", "closed"):
        warnings.append("Há gasto registrado sem aprovação do experimento.")
    if t["spend"] > exp.budget_cap_cents:
        warnings.append(f"Gasto passou do teto aprovado ({t['spend']} > {exp.budget_cap_cents} centavos).")
    return {
        "spend_cents": t["spend"],
        "sales_count": t["sales"],
        "gross_cents": t["gross"],
        "fees_cents": t["fees"],
        "refunded_cents": t["refunded"],
        "net_revenue_cents": net,
        "profit_cents": profit,
        "roi_percent": round(profit / t["spend"] * 100, 2) if t["spend"] > 0 else None,
        "cpa_cents": cpa,
        "break_even_cpa_cents": be,
        "budget_used_percent": round(t["spend"] / exp.budget_cap_cents * 100, 2),
        "warnings": warnings,
        **recommend(exp, t["spend"], t["sales"], cpa, be),
    }


def recommend(exp: Experiment, spend: int, sales: int, cpa: int | None, break_even: int) -> dict:
    """Primeira regra que casar vence. `action`: not_started | continue | stop | validated_candidate | closed."""
    if exp.status == "closed":
        return {"action": "closed", "reason": f"Encerrado pelo proprietário ({exp.outcome})."}
    if exp.status != "approved":
        return {"action": "not_started", "reason": "Aguardando aprovação para começar; nenhum gasto autorizado ainda."}
    if spend >= exp.budget_cap_cents:
        return {"action": "stop", "reason": "Teto de orçamento atingido."}
    if sales == 0 and spend >= exp.max_spend_without_sale_cents:
        return {"action": "stop", "reason": "Gastou o limite definido sem nenhuma venda."}
    if sales < exp.min_sales_to_decide:
        return {"action": "continue",
                "reason": f"Evidência insuficiente: {sales} de {exp.min_sales_to_decide} vendas para decidir."}
    if cpa is not None and cpa <= break_even:
        return {"action": "validated_candidate",
                "reason": "CPA dentro do ponto de equilíbrio com a evidência mínima. Elegível a validar; "
                          "não é garantia de lucro e escalar exige sua aprovação."}
    return {"action": "stop", "reason": "CPA acima do ponto de equilíbrio com a evidência mínima."}


def request_approval_details(exp: Experiment) -> tuple[dict, str]:
    details = {
        "experiment_id": exp.id, "name": exp.name, "market": exp.market, "currency": exp.currency,
        "budget_cap_cents": exp.budget_cap_cents, "max_spend_without_sale_cents": exp.max_spend_without_sale_cents,
        "min_sales_to_decide": exp.min_sales_to_decide, "break_even_cpa_cents": break_even_cpa_cents(exp),
    }
    consequences = (
        f"{policy.consequences_for('activate_campaign')} Autoriza gastar até {exp.budget_cap_cents} centavos "
        f"({exp.currency}) neste teste. O sistema NÃO gasta: você roda a campanha e registra gasto e vendas."
    )
    return details, consequences


def close(db: Session, exp: Experiment, outcome: str, note: str) -> None:
    if exp.status != "approved":
        raise ExperimentError("Só é possível encerrar um experimento aprovado e em andamento.")
    if outcome == "validated":
        m = metrics(db, exp)
        if m["action"] != "validated_candidate":
            raise ExperimentError(f"Não pode ser marcada como validada: {m['reason']}")
    exp.status = "closed"
    exp.outcome = outcome
    exp.outcome_note = note
    exp.closed_at = datetime.now(timezone.utc)
