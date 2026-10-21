"""BMW workflow, supplier allocation, finance ledger, and document sharing."""
from alembic import op
import sqlalchemy as sa

revision = "0002_bmw_workflow"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("suppliers") as batch:
        batch.add_column(sa.Column("business_registration", sa.String(100), nullable=True))
        batch.add_column(sa.Column("website", sa.String(255), nullable=True))
        batch.add_column(sa.Column("preferred_currency", sa.String(3), nullable=False, server_default="EUR"))
        batch.add_column(sa.Column("typical_lead_time_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("bank_details", sa.Text(), nullable=True))
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("business_name", sa.String(180), nullable=True))
        batch.add_column(sa.Column("nic_tax_id", sa.String(100), nullable=True))
        batch.add_column(sa.Column("billing_address", sa.Text(), nullable=True))
        batch.add_column(sa.Column("preferred_contact", sa.String(20), nullable=False, server_default="WhatsApp"))
        batch.create_index("ix_customers_nic_tax_id", ["nic_tax_id"], unique=False)
    with op.batch_alter_table("vehicles") as batch:
        batch.add_column(sa.Column("color", sa.String(50), nullable=True))
        batch.add_column(sa.Column("mileage_km", sa.Integer(), nullable=True))
    with op.batch_alter_table("customer_quotation_items") as batch:
        batch.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("supplier_reference", sa.String(100), nullable=True))
        batch.add_column(sa.Column("unit_cost_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key("fk_quote_item_supplier", "suppliers", ["supplier_id"], ["id"])
        batch.create_index("ix_customer_quotation_items_supplier_id", ["supplier_id"], unique=False)
    with op.batch_alter_table("sales_order_items") as batch:
        batch.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("supplier_reference", sa.String(100), nullable=True))
        batch.create_foreign_key("fk_order_item_supplier", "suppliers", ["supplier_id"], ["id"])
        batch.create_index("ix_sales_order_items_supplier_id", ["supplier_id"], unique=False)
    with op.batch_alter_table("sales_orders") as batch:
        batch.add_column(sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("additional_charges_cents", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "finance_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_finance_entries_entry_date", "finance_entries", ["entry_date"])
    op.create_index("ix_finance_entries_entry_type", "finance_entries", ["entry_type"])
    op.create_index("ix_finance_entries_category", "finance_entries", ["category"])
    op.create_table(
        "document_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_document_shares_document_type", "document_shares", ["document_type"])
    op.create_index("ix_document_shares_document_id", "document_shares", ["document_id"])
    op.create_index("ix_document_shares_token_hash", "document_shares", ["token_hash"])
    op.create_index("ix_document_shares_expires_at", "document_shares", ["expires_at"])


def downgrade():
    op.drop_table("document_shares")
    op.drop_table("finance_entries")
    with op.batch_alter_table("sales_orders") as batch:
        batch.drop_column("additional_charges_cents")
        batch.drop_column("discount_cents")
    with op.batch_alter_table("sales_order_items") as batch:
        batch.drop_index("ix_sales_order_items_supplier_id")
        batch.drop_constraint("fk_order_item_supplier", type_="foreignkey")
        batch.drop_column("supplier_reference")
        batch.drop_column("supplier_id")
    with op.batch_alter_table("customer_quotation_items") as batch:
        batch.drop_index("ix_customer_quotation_items_supplier_id")
        batch.drop_constraint("fk_quote_item_supplier", type_="foreignkey")
        batch.drop_column("unit_cost_cents")
        batch.drop_column("supplier_reference")
        batch.drop_column("supplier_id")
    with op.batch_alter_table("vehicles") as batch:
        batch.drop_column("mileage_km")
        batch.drop_column("color")
    with op.batch_alter_table("customers") as batch:
        batch.drop_index("ix_customers_nic_tax_id")
        batch.drop_column("preferred_contact")
        batch.drop_column("billing_address")
        batch.drop_column("nic_tax_id")
        batch.drop_column("business_name")
    with op.batch_alter_table("suppliers") as batch:
        batch.drop_column("bank_details")
        batch.drop_column("typical_lead_time_days")
        batch.drop_column("preferred_currency")
        batch.drop_column("website")
        batch.drop_column("business_registration")
