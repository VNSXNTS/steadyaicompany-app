"""etapa, evento sazonal e preparação de lançamento nos experimentos

Revision ID: 0003
Revises: 0002

Colunas novas em `experiments` com valor padrão no banco (linhas antigas viram etapa "validation",
sem evento, sem ângulos e sem checklist: nada do que existia muda de significado).
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch:
        batch.add_column(sa.Column("stage", sa.String(20), nullable=False, server_default="validation"))
        batch.add_column(sa.Column("parent_experiment_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("event_name", sa.String(150), nullable=True))
        batch.add_column(sa.Column("event_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("creative_angles", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("launch_checklist", sa.JSON(), nullable=False, server_default="{}"))
        batch.create_foreign_key("fk_experiments_parent_experiment_id", "experiments",
                                 ["parent_experiment_id"], ["id"])


def downgrade() -> None:
    # DESTRUTIVO para estes campos (etapa, evento, ângulos, checklist). Faça backup antes (docs/BANCO.md).
    with op.batch_alter_table("experiments") as batch:
        batch.drop_constraint("fk_experiments_parent_experiment_id", type_="foreignkey")
        for col in ("launch_checklist", "creative_angles", "event_date", "event_name",
                    "parent_experiment_id", "stage"):
            batch.drop_column(col)
