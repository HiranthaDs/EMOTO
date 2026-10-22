"""POS checkout, service history, and landed inventory costs."""
from alembic import op
import sqlalchemy as sa

revision = "0004_pos_services"
down_revision = "0003_inventory_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_fee_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("recommended_interval_km", sa.Integer(), nullable=True),
        sa.Column("recommended_interval_months", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="Active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_services_code", "services", ["code"])
    op.create_index("ix_services_name", "services", ["name"])
    op.create_index("ix_services_category", "services", ["category"])
    op.create_index("ix_services_status", "services", ["status"])

    with op.batch_alter_table("inventory_movements") as batch:
        batch.add_column(sa.Column("overhead_cost_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("landed_unit_cost_cents", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE inventory_movements SET landed_unit_cost_cents = unit_cost_cents")

    for table, constraint in [
        ("customer_quotation_items", "fk_quote_item_service"),
        ("sales_order_items", "fk_order_item_service"),
        ("invoice_items", "fk_invoice_item_service"),
    ]:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("service_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(constraint, "services", ["service_id"], ["id"])

    op.create_table(
        "service_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("odometer_km", sa.Integer(), nullable=True),
        sa.Column("technician", sa.String(120), nullable=True),
        sa.Column("next_service_date", sa.Date(), nullable=True),
        sa.Column("next_service_km", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_service_records_number", "service_records", ["number"])
    op.create_index("ix_service_records_customer_id", "service_records", ["customer_id"])
    op.create_index("ix_service_records_vehicle_id", "service_records", ["vehicle_id"])
    op.create_index("ix_service_records_invoice_id", "service_records", ["invoice_id"])
    op.create_index("ix_service_records_service_date", "service_records", ["service_date"])
    op.create_table(
        "service_record_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_record_id", sa.Integer(), sa.ForeignKey("service_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("parts.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_service_record_items_service_record_id", "service_record_items", ["service_record_id"])


def downgrade():
    op.drop_table("service_record_items")
    op.drop_table("service_records")
    for table, constraint in [
        ("invoice_items", "fk_invoice_item_service"),
        ("sales_order_items", "fk_order_item_service"),
        ("customer_quotation_items", "fk_quote_item_service"),
    ]:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="foreignkey")
            batch.drop_column("service_id")
    with op.batch_alter_table("inventory_movements") as batch:
        batch.drop_column("landed_unit_cost_cents")
        batch.drop_column("overhead_cost_cents")
    op.drop_table("services")
