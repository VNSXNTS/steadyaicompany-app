"""CEO Agent: delega tarefas aos especialistas e gera o relatório executivo.

Nesta versão o CEO segue um roteiro fixo (sem decidir com IA). Ele cria tarefas
encadeadas por dependência e nunca executa o trabalho dos especialistas.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Agent, Approval, Task, TaskStatus
from app.services.tasks import TaskError, audit, create_task, next_runnable, run_task
from app.services.llm import LLMProvider

# (agente, descrição, índices das etapas das quais depende, ação de risco)
NEW_PRODUCT_PIPELINE = [
    ("market_hunter", "Pesquisar dores e sinais de demanda do público para: {goal}", [], None),
    ("competitor_analyst", "Analisar ofertas, preços, bônus e posicionamento dos concorrentes para: {goal}", [0], None),
    ("strategy", "Avaliar a oportunidade, riscos, custos e nível de confiança; recomendar produto para: {goal}", [0, 1], None),
    ("product_architect", "Definir estrutura, módulos, formato e especificação do produto para: {goal}", [2], None),
    ("product_creator", "Produzir os arquivos do produto (rascunho em ambiente de teste) para: {goal}", [3], None),
    ("quality_guardian", "Revisar os arquivos contra os critérios de aprovação; barrar se incompleto: {goal}", [4], None),
    ("creative_director", "Criar rascunhos de conceitos, roteiros e textos de anúncio (sem publicar) para: {goal}", [5], None),
    ("growth_strategist", "Planejar canais, funil e orçamento de teste para: {goal}", [5], None),
    ("sales_manager", "Preparar revisão da página de vendas e plano de acompanhamento de conversão para: {goal}", [6, 7], None),
    ("growth_strategist", "Publicar anúncios pagos para: {goal}", [8], "publish_paid_ads"),
]

# Roteiro com FERRAMENTAS reais (sem IA, rede nem custo): gera a planilha Steady Payoff, manda o Quality
# Guardian revisá-la e fecha com os números registrados. Itens: (agente, descrição, dependências, ação, entrada
# extra). "$step:N" na entrada vira o id da tarefa da etapa N. Não há etapa de risco: nada é publicado nem gasto.
STEADY_PAYOFF_BUILD_PIPELINE = [
    ("product_creator", "Gerar a planilha Steady Payoff (dados de exemplo identificados) para: {goal}", [], None,
     {"tool": "steady_payoff_xlsx"}),
    ("quality_guardian", "Revisar a planilha gerada: hash, fórmulas, recálculo e valores para: {goal}", [0], None,
     {"tool": "review_xlsx", "product_task_id": "$step:0"}),
    ("sales_manager", "Relatório de vendas e reembolsos registrados para: {goal}", [1], None,
     {"tool": "sales_report"}),
    ("cfo", "Resumo financeiro registrado (receita líquida, lucro) para: {goal}", [1], None,
     {"tool": "financial_summary"}),
]

PIPELINES = {"new_product": NEW_PRODUCT_PIPELINE, "steady_payoff_build": STEADY_PAYOFF_BUILD_PIPELINE}
PIPELINE_LABELS = {
    "new_product": "Novo produto (agentes com IA; a última etapa, anúncio pago, para e pede sua aprovação)",
    "steady_payoff_build": "Steady Payoff: gerar e revisar a planilha (ferramentas, sem IA, sem custo, sem risco)",
}


def plan_goal(db: Session, goal: str, pipeline: str = "new_product", priority: int = 3) -> list[Task]:
    if pipeline not in PIPELINES:
        raise TaskError(f"Roteiro desconhecido: {pipeline}")
    if not goal.strip():
        raise TaskError("O objetivo não pode ser vazio")
    created: list[Task] = []
    for step in PIPELINES[pipeline]:
        agent_key, template, dep_idx, action = step[:4]
        extra = {k: (created[int(v.split(":")[1])].id if isinstance(v, str) and v.startswith("$step:") else v)
                 for k, v in (step[4] if len(step) > 4 else {}).items()}
        task = create_task(
            db, agent_key, template.format(goal=goal.strip()),
            priority=priority, action=action,
            depends_on=[created[i].id for i in dep_idx],
            input={"goal": goal.strip(), "pipeline": pipeline, **extra},
            actor="ceo",
        )
        created.append(task)
    audit(db, "ceo", "goal_planned", {"goal": goal, "tasks": [t.id for t in created]})
    db.commit()
    return created


def run_next(db: Session, provider: LLMProvider | None = None) -> Task | None:
    task = next_runnable(db)
    if task is None:
        return None
    return run_task(db, task, provider)


def run_until_blocked(db: Session, provider: LLMProvider | None = None, limit: int = 50) -> list[Task]:
    """Roda tarefas prontas até não restar nenhuma (ou o limite). Para nas aprovações."""
    ran = []
    for _ in range(limit):
        try:
            task = run_next(db, provider)
        except TaskError:  # ex.: orçamento de IA não autorizado. Para aqui; o resto segue pendente.
            break
        if task is None:
            break
        ran.append(task)
    return ran


def executive_report(db: Session) -> dict:
    counts = dict(db.execute(select(Task.status, func.count()).group_by(Task.status)).all())
    pending_approvals = db.scalar(
        select(func.count()).select_from(Approval).where(Approval.status == "pending")) or 0
    failed = db.scalars(select(Task).where(Task.status == TaskStatus.FAILED)).all()
    blocked = db.scalars(
        select(Task).where(Task.status == TaskStatus.PENDING)
    ).all()
    paused = [a.key for a in db.scalars(select(Agent).where(Agent.status == "paused"))]
    reviews = [t for t in db.scalars(select(Task).where(Task.status == TaskStatus.COMPLETED,
                                                        Task.agent_key == "quality_guardian")).all()
               if ((t.output or {}).get("result") or {}).get("verdict")]
    rejected = [t.id for t in reviews if t.output["result"]["verdict"] == "rejected"]
    with_gaps = [t.id for t in reviews if t.output["result"]["verdict"] == "approved_with_gaps"]
    return {
        "tasks_by_status": {s: counts.get(s, 0) for s in TaskStatus.ALL},
        "pending_approvals": pending_approvals,
        "failed_tasks": [{"id": t.id, "agent": t.agent_key, "error": t.error} for t in failed],
        "waiting_tasks": len(blocked),
        "paused_agents": paused,
        "quality_rejected_tasks": rejected,  # revisão do Quality Guardian que barrou o produto
        "quality_gap_tasks": with_gaps,  # aprovado, mas com verificações que não puderam rodar
        "attention_needed": bool(failed or pending_approvals or paused or rejected or with_gaps),
    }
