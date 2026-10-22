"""Store duration-based warranty terms throughout the sales workflow."""
from alembic import op
import sqlalchemy as sa

revision = "0005_warranty_durations"
down_revision = "0004_pos_services"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("customer_quotation_items", "sales_order_items", "invoice_items"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("warranty_days", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    for table in ("invoice_items", "sales_order_items", "customer_quotation_items"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("warranty_days")
