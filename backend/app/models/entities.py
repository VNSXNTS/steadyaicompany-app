from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ALL = (PENDING, RUNNING, AWAITING_APPROVAL, COMPLETED, FAILED, CANCELLED)


class Agent(Base):
    __tablename__ = "agents"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    department: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused
    model: Mapped[str] = mapped_column(String(100), default="")
    can_spend: Mapped[bool] = mapped_column(Boolean, default=False)  # nunca True para agentes
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[int] = mapped_column(Integer)
    blocked_until: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_status_priority", "status", "priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_key: Mapped[str] = mapped_column(ForeignKey("agents.key"))
    department: Mapped[str] = mapped_column(String(50), default="")
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 = mais alta, 5 = mais baixa
    status: Mapped[str] = mapped_column(String(30), default=TaskStatus.PENDING)
    action: Mapped[str | None] = mapped_column(String(60), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list["TaskLog"]] = relationship(back_populates="task", order_by="TaskLog.id")


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    event: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text, default="")

    task: Mapped[Task] = relationship(back_populates="logs")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    consequences: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    # pending | approved | rejected | changes_requested
    decision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    niche: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    # draft | in_review | approved | published
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Sale(Base):
    """Venda registrada. Valores em centavos. Receita líquida = bruto - taxas - reembolsos."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    gross_cents: Mapped[int] = mapped_column(Integer)
    fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50))  # ads | hosting | ai | tools | other
    description: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Experiment(Base):
    """Teste de validação de uma oferta com orçamento pequeno e critérios de parada definidos ANTES de gastar.

    O sistema não gasta nem publica nada: o proprietário roda a campanha fora e registra gasto e vendas.
    Dinheiro em centavos da `currency` do experimento. Teto e critérios não podem ser editados depois de criados.
    """

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    market: Mapped[str] = mapped_column(String(10))  # ex.: US, BR (sem padrão: decisão do proprietário)
    currency: Mapped[str] = mapped_column(String(3))  # ex.: USD, BRL (sem padrão)
    price_cents: Mapped[int] = mapped_column(Integer)
    fee_bps: Mapped[int] = mapped_column(Integer, default=0)  # taxa percentual em pontos-base (499 = 4,99%)
    fee_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    budget_cap_cents: Mapped[int] = mapped_column(Integer)
    max_spend_without_sale_cents: Mapped[int] = mapped_column(Integer)
    min_sales_to_decide: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    # draft | pending_approval | approved | rejected | closed
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)  # killed | validated
    outcome_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Fase 16b: etapa, evento sazonal e preparação de lançamento (atestada pelo proprietário).
    stage: Mapped[str] = mapped_column(String(20), default="validation", server_default="validation")
    # validation | scale (scale só nasce de um experimento validado: parent_experiment_id)
    parent_experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # data (UTC) em que a demanda sazonal acaba
    creative_angles: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # [{angle, hook}]
    launch_checklist: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # {item: bool}


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(50))  # admin | ceo | system
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class AIUsage(Base):
    """Cada chamada a um provedor de IA. Custo em milionésimos de dólar (0 para modelos locais)."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micro_usd: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
