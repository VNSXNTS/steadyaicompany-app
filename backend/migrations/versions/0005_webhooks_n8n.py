"""recibos de idempotência dos webhooks do n8n

Revision ID: 0005
Revises: 0004

Tabela nova `webhook_receipts` (chave única = Idempotency-Key). Não altera nenhuma tabela existente.
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_receipts",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_receipts_task_id", "webhook_receipts", ["task_id"])


def downgrade() -> None:
    # Apaga os recibos: depois disso, um reenvio antigo do n8n com a mesma chave criaria tarefa duplicada.
    op.drop_index("ix_webhook_receipts_task_id", table_name="webhook_receipts")
    op.drop_table("webhook_receipts")
