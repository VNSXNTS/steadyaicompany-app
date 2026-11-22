"""experimentos de validação de oferta

Revision ID: 0002
Revises: 0001

Cria `experiments` e liga gastos e vendas a um experimento (colunas nulas: dados antigos não mudam).
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("fee_fixed_cents", sa.Integer(), nullable=False),
        sa.Column("budget_cap_cents", sa.Integer(), nullable=False),
        sa.Column("max_spend_without_sale_cents", sa.Integer(), nullable=False),
        sa.Column("min_sales_to_decide", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for table in ("sales", "expenses"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("experiment_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_experiment_id", "experiments", ["experiment_id"], ["id"])
            batch.create_index(f"ix_{table}_experiment_id", ["experiment_id"])


def downgrade() -> None:
    # DESTRUTIVO para os dados de experimentos. Faça backup antes (docs/BANCO.md).
    for table in ("expenses", "sales"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_experiment_id")
            batch.drop_constraint(f"fk_{table}_experiment_id", type_="foreignkey")
            batch.drop_column("experiment_id")
    op.drop_table("experiments")
