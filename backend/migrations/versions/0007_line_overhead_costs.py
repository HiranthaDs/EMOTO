"""Track private overhead costs on quotation and order lines."""

from alembic import op
import sqlalchemy as sa


revision = "0007_line_overhead_costs"
down_revision = "0006_initial_admin_login"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("customer_quotation_items", "sales_order_items"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("overhead_cost_cents", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    for table in ("sales_order_items", "customer_quotation_items"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("overhead_cost_cents")
