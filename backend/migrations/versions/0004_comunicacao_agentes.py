"""mensagens e handoffs entre agentes

Revision ID: 0004
Revises: 0003

Tabela nova `agent_messages` (só acrescenta). Não altera nenhuma tabela existente.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("from_agent", sa.String(), sa.ForeignKey("agents.key"), nullable=False),
        sa.Column("to_agent", sa.String(), sa.ForeignKey("agents.key"), nullable=False),
        sa.Column("subject", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("handoff_task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("agent_messages.id"), nullable=True),
        sa.Column("hop", sa.Integer(), nullable=False),
    )
    op.create_index("ix_agent_messages_from_agent", "agent_messages", ["from_agent"])
    op.create_index("ix_agent_messages_to_agent", "agent_messages", ["to_agent"])
    op.create_index("ix_agent_messages_task_id", "agent_messages", ["task_id"])


def downgrade() -> None:
    # DESTRUTIVO: apaga o histórico de mensagens entre agentes. Faça backup antes (docs/BANCO.md).
    op.drop_index("ix_agent_messages_task_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_to_agent", table_name="agent_messages")
    op.drop_index("ix_agent_messages_from_agent", table_name="agent_messages")
    op.drop_table("agent_messages")
