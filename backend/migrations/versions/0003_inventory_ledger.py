"""Detailed inventory ledger and weighted stock valuation."""
from alembic import op
import sqlalchemy as sa

revision = "0003_inventory_ledger"
down_revision = "0002_bmw_workflow"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("parts") as batch:
        batch.add_column(sa.Column("barcode", sa.String(100), nullable=True))
        batch.add_column(sa.Column("unit_of_measure", sa.String(30), nullable=False, server_default="Each"))
        batch.add_column(sa.Column("condition", sa.String(30), nullable=False, server_default="New"))
        batch.add_column(sa.Column("country_of_origin", sa.String(80), nullable=True))
        batch.add_column(sa.Column("last_purchase_cost_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reorder_quantity", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("maximum_stock", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("storage_bin", sa.String(80), nullable=True))
        batch.add_column(sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_parts_barcode", ["barcode"], unique=False)

    with op.batch_alter_table("inventory_movements") as batch:
        batch.add_column(sa.Column("number", sa.String(40), nullable=True))
        batch.add_column(sa.Column("quantity_delta", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reserved_delta", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("quantity_before", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("quantity_after", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reserved_before", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reserved_after", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("unit_cost_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("total_cost_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("stock_value_before_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("stock_value_after_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("movement_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")))
        batch.add_column(sa.Column("document_reference", sa.String(100), nullable=True))
        batch.add_column(sa.Column("batch_number", sa.String(100), nullable=True))
        batch.add_column(sa.Column("location", sa.String(100), nullable=True))
        batch.create_foreign_key("fk_inventory_movement_supplier", "suppliers", ["supplier_id"], ["id"])

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM inventory_movements ORDER BY id")).fetchall()
    for row in rows:
        connection.execute(
            sa.text("UPDATE inventory_movements SET number = :number WHERE id = :id"),
            {"number": f"MOV-LEGACY-{row[0]:05d}", "id": row[0]},
        )

    with op.batch_alter_table("inventory_movements") as batch:
        batch.alter_column("number", existing_type=sa.String(40), nullable=False)
        batch.create_index("ix_inventory_movements_number", ["number"], unique=True)
        batch.create_index("ix_inventory_movements_supplier_id", ["supplier_id"], unique=False)
        batch.create_index("ix_inventory_movements_movement_date", ["movement_date"], unique=False)
        batch.create_index("ix_inventory_movements_document_reference", ["document_reference"], unique=False)
        batch.create_index("ix_inventory_movements_batch_number", ["batch_number"], unique=False)

    op.execute("UPDATE parts SET last_purchase_cost_cents = purchase_cost_cents WHERE last_purchase_cost_cents = 0")


def downgrade():
    with op.batch_alter_table("inventory_movements") as batch:
        batch.drop_index("ix_inventory_movements_batch_number")
        batch.drop_index("ix_inventory_movements_document_reference")
        batch.drop_index("ix_inventory_movements_movement_date")
        batch.drop_index("ix_inventory_movements_supplier_id")
        batch.drop_index("ix_inventory_movements_number")
        batch.drop_constraint("fk_inventory_movement_supplier", type_="foreignkey")
        batch.drop_column("location")
        batch.drop_column("batch_number")
        batch.drop_column("document_reference")
        batch.drop_column("movement_date")
        batch.drop_column("supplier_id")
        batch.drop_column("stock_value_after_cents")
        batch.drop_column("stock_value_before_cents")
        batch.drop_column("total_cost_cents")
        batch.drop_column("unit_cost_cents")
        batch.drop_column("reserved_after")
        batch.drop_column("reserved_before")
        batch.drop_column("quantity_after")
        batch.drop_column("quantity_before")
        batch.drop_column("reserved_delta")
        batch.drop_column("quantity_delta")
        batch.drop_column("number")

    with op.batch_alter_table("parts") as batch:
        batch.drop_index("ix_parts_barcode")
        batch.drop_column("last_received_at")
        batch.drop_column("storage_bin")
        batch.drop_column("maximum_stock")
        batch.drop_column("reorder_quantity")
        batch.drop_column("last_purchase_cost_cents")
        batch.drop_column("country_of_origin")
        batch.drop_column("condition")
        batch.drop_column("unit_of_measure")
        batch.drop_column("barcode")
