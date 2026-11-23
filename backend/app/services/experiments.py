"""Experimentos de validação de oferta: métricas e recomendação por regras.

Princípios (do método de validar com pouco orçamento, e das regras do projeto):
- Teto de gasto e critérios de parada são definidos ANTES de gastar e não podem ser editados.
- O sistema RECOMENDA; quem decide encerrar ou validar é o proprietário.
- Só se pode marcar "validada" uma oferta que cumpriu as regras de evidência e de CPA.
- Dinheiro em centavos. ROI e CPA são `None` quando não há base (nunca 0 inventado).
- Receita líquida = bruto - taxas - reembolsos. Lucro = líquida - despesas do experimento.
- Uma recomendação NÃO é garantia de lucro: poucas vendas são evidência fraca.
- Fase 16b: validar primeiro, escalar depois. Uma etapa `scale` só nasce de um experimento VALIDADO e precisa
  de nova aprovação. Antes de pedir aprovação, o proprietário atesta um checklist e define >= 3 ângulos de
  criativo. Evento sazonal: passou a data, sem evidência suficiente => parar. O sistema não verifica o
  checklist no mundo real: é uma atestação do proprietário, registrada.
"""
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Expense, Experiment, Sale
from app.services import policy


class ExperimentError(Exception):
    pass


MIN_CREATIVE_ANGLES = 3
EVENT_WARNING_DAYS = 7  # heurística: poucos dias até o evento = pouco tempo para juntar evidência
# Itens que o PROPRIETÁRIO atesta (o sistema não consegue conferi-los fora daqui). Todos obrigatórios.
LAUNCH_CHECKLIST = {
    "checkout_tested": "Fiz uma compra de teste no checkout e o arquivo foi entregue.",
    "purchase_event_configured": "O evento de compra está configurado para o anúncio medir vendas.",
    "refund_policy_published": "A política de reembolso está publicada e visível antes da compra.",
    "no_result_guarantee_claims": "Anúncio e página não prometem resultado garantido nem usam depoimento inventado.",
}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def days_to_event(exp: Experiment, today: date | None = None) -> int | None:
    return None if exp.event_date is None else (exp.event_date - (today or _today())).days


def launch_blockers(exp: Experiment, today: date | None = None) -> list[str]:
    """O que impede pedir aprovação. Lista vazia = pode pedir (a decisão continua sendo do proprietário)."""
    blockers = [f"Checklist pendente: {text}" for key, text in LAUNCH_CHECKLIST.items()
                if exp.launch_checklist.get(key) is not True]
    names = {a["angle"].strip().lower() for a in exp.creative_angles if a.get("angle", "").strip()
             and a.get("hook", "").strip()}
    if len(names) < MIN_CREATIVE_ANGLES:
        blockers.append(f"Defina pelo menos {MIN_CREATIVE_ANGLES} ângulos de criativo distintos, cada um com "
                        f"gancho (hoje: {len(names)}).")
    d = days_to_event(exp, today)
    if d is not None and d < 0:
        blockers.append("A data do evento sazonal já passou.")
    return blockers


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


def metrics(db: Session, exp: Experiment, today: date | None = None) -> dict:
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
    d = days_to_event(exp, today)
    if d is not None and 0 <= d <= EVENT_WARNING_DAYS and exp.status not in ("closed", "rejected"):
        warnings.append(f"Faltam {d} dia(s) para o evento sazonal: pouco tempo para juntar evidência.")
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
        "days_to_event": d,
        "launch_blockers": launch_blockers(exp, today) if exp.status == "draft" else [],
        "warnings": warnings,
        **recommend(exp, t["spend"], t["sales"], cpa, be, today),
    }


def recommend(exp: Experiment, spend: int, sales: int, cpa: int | None, break_even: int,
              today: date | None = None) -> dict:
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
        d = days_to_event(exp, today)
        if d is not None and d < 0:
            return {"action": "stop", "reason": f"O evento sazonal ({exp.event_name or 'sem nome'}) já passou "
                                                f"sem evidência suficiente ({sales} de {exp.min_sales_to_decide} vendas)."}
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
        "stage": exp.stage, "parent_experiment_id": exp.parent_experiment_id,
        "event_name": exp.event_name, "event_date": exp.event_date.isoformat() if exp.event_date else None,
        "creative_angles": exp.creative_angles, "launch_checklist": exp.launch_checklist,
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


def assert_can_request_approval(db: Session, exp: Experiment, today: date | None = None) -> None:
    if exp.status != "draft":
        raise ExperimentError(f"Só um rascunho pede aprovação (status atual: {exp.status})")
    blockers = launch_blockers(exp, today)
    if blockers:
        raise ExperimentError("Preparação de lançamento incompleta: " + " | ".join(blockers))


def create_scale_stage(db: Session, parent: Experiment, name: str, budget_cap_cents: int,
                       max_spend_without_sale_cents: int, min_sales_to_decide: int) -> Experiment:
    """Escala SÓ a partir de um experimento validado. Herda preço, taxas, mercado, moeda, evento e ângulos;
    o checklist recomeça vazio (nova campanha, nova atestação) e precisa de aprovação nova."""
    if parent.status != "closed" or parent.outcome != "validated":
        raise ExperimentError("Só se escala um experimento encerrado como VALIDADO. Valide primeiro.")
    if parent.stage != "validation":
        raise ExperimentError("A escala parte de um experimento de validação, não de outra escala.")
    if budget_cap_cents <= parent.budget_cap_cents:
        raise ExperimentError("O teto da escala deve ser maior que o teto da validação "
                              f"({parent.budget_cap_cents} centavos).")
    if max_spend_without_sale_cents > budget_cap_cents:
        raise ExperimentError("max_spend_without_sale_cents não pode passar do teto (budget_cap_cents).")
    open_child = db.scalar(select(Experiment.id).where(
        Experiment.parent_experiment_id == parent.id, Experiment.status.notin_(("closed", "rejected"))))
    if open_child is not None:
        raise ExperimentError(f"Já existe uma escala em aberto para este experimento (#{open_child}).")
    child = Experiment(
        name=name, product_id=parent.product_id, market=parent.market, currency=parent.currency,
        price_cents=parent.price_cents, fee_bps=parent.fee_bps, fee_fixed_cents=parent.fee_fixed_cents,
        budget_cap_cents=budget_cap_cents, max_spend_without_sale_cents=max_spend_without_sale_cents,
        min_sales_to_decide=min_sales_to_decide, stage="scale", parent_experiment_id=parent.id,
        event_name=parent.event_name, event_date=parent.event_date,
        creative_angles=[dict(a) for a in parent.creative_angles], launch_checklist={},
    )
    db.add(child)
    db.flush()
    return child
