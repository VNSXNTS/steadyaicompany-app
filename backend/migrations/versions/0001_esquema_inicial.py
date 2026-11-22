"""esquema inicial

Revision ID: 0001
Revises:

Idempotente DE PROPÓSITO: bancos criados pela v0.2 (Base.metadata.create_all, sem Alembic) já têm
a maioria destas tabelas. Aqui cada tabela só é criada se ainda não existir, então um banco antigo
é adotado sem perda de dados e ganha apenas as tabelas que faltam (users, auth_sessions,
login_attempts). Nenhuma tabela existente é alterada ou apagada no upgrade.
Limite conhecido: se uma tabela antiga tiver colunas diferentes das esperadas, esta migração não
as corrige; mudanças de coluna entram em migrações posteriores (0002, ...).
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Ordem de criação respeita as chaves estrangeiras; o downgrade usa a ordem inversa.
TABLES = [
    "agents", "audit_logs", "expenses", "login_attempts", "products", "users", "auth_sessions",
    "sales", "tasks", "ai_usage", "approvals", "task_logs",
]


def _create(name: str, *items, indexes=()) -> None:
    if sa.inspect(op.get_bind()).has_table(name):
        return
    op.create_table(name, *items)
    for index_name, columns, unique in indexes:
        op.create_index(index_name, name, columns, unique=unique)


def upgrade() -> None:
    _create(
        "agents",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("department", sa.String(50), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("can_spend", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    _create(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(50), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    _create(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create(
        "login_attempts",
        sa.Column("ip_hash", sa.String(64), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.Integer(), nullable=True),
    )
    _create(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("niche", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        indexes=[("ix_users_email", ["email"], True)],
    )
    _create(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        indexes=[("ix_auth_sessions_expires_at", ["expires_at"], False),
                 ("ix_auth_sessions_user_id", ["user_id"], False)],
    )
    _create(
        "sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("gross_cents", sa.Integer(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=False),
        sa.Column("refunded_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_key", sa.String(50), sa.ForeignKey("agents.key"), nullable=False),
        sa.Column("department", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("action", sa.String(60), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        indexes=[("ix_tasks_status_priority", ["status", "priority"], False)],
    )
    _create(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micro_usd", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        indexes=[("ix_ai_usage_created_at", ["created_at"], False),
                 ("ix_ai_usage_task_id", ["task_id"], False)],
    )
    _create(
        "approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("consequences", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        indexes=[("ix_approvals_task_id", ["task_id"], False)],
    )
    _create(
        "task_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        indexes=[("ix_task_logs_task_id", ["task_id"], False)],
    )


def downgrade() -> None:
    # DESTRUTIVO: apaga todas as tabelas da aplicação. Faça backup antes (docs/BANCO.md).
    for name in reversed(TABLES):
        if sa.inspect(op.get_bind()).has_table(name):
            op.drop_table(name)
