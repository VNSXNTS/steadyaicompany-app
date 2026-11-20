"""Registro dos 13 agentes. Nenhum agente tem permissão de gastar dinheiro."""
from sqlalchemy.orm import Session

from app.models.entities import Agent

AGENT_DEFS = [
    ("ceo", "CEO Agent", "executive",
     "Coordena os agentes, distribui e prioriza tarefas, pede aprovações e gera relatórios executivos. Delega, não executa tudo."),
    ("market_hunter", "Market Hunter", "research",
     "Pesquisa nichos, tendências e dores do público. Anúncio ativo não prova que uma oferta vende."),
    ("competitor_analyst", "Competitor Analyst", "research",
     "Analisa páginas, ofertas, preços, bônus, posicionamento e funis dos concorrentes."),
    ("strategy", "Chief Strategy Officer", "strategy",
     "Compara oportunidades, estima custos e riscos. Toda decisão traz justificativa e nível de confiança."),
    ("product_architect", "Product Architect", "product",
     "Define estrutura, módulos, bônus, formato e especificação dos produtos."),
    ("product_creator", "Product Creator", "product",
     "Produz os arquivos reais do produto (XLSX, PDF, DOCX). Entrega arquivos, não descrições."),
    ("quality_guardian", "Quality Guardian", "quality",
     "Revisa, confere cálculos e impede produto incompleto de avançar para publicação."),
    ("growth_strategist", "Growth Strategist", "growth",
     "Define canais, funis e testes. Campanhas pagas só com aprovação."),
    ("creative_director", "Creative Director", "creative",
     "Cria conceitos, roteiros, textos e prompts de criativos. Não publica sem aprovação."),
    ("social_media", "Social Media Manager", "growth",
     "Planeja calendário e conteúdos. Publica só via integração oficial e autorizada."),
    ("sales_manager", "Sales Manager", "sales",
     "Monitora conversão e funis, aponta abandono e recomenda melhorias."),
    ("customer_success", "Customer Success", "support",
     "Responde dúvidas com documentação aprovada. Não inventa política nem promete reembolso."),
    ("cfo", "CFO & Performance Analyst", "finance",
     "Calcula receita líquida, lucro e margem. Nunca confunde faturamento com lucro."),
]

AGENT_KEYS = [d[0] for d in AGENT_DEFS]


def seed_agents(db: Session, model_name: str = "") -> int:
    """Cria os agentes que ainda não existem. Idempotente."""
    created = 0
    for key, name, department, role in AGENT_DEFS:
        if db.get(Agent, key) is None:
            db.add(Agent(key=key, name=name, department=department, role=role,
                         model=model_name, can_spend=False))
            created += 1
    db.commit()
    return created
