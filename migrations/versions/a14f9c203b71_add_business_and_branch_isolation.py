"""add tenant and branch ownership to POS records

Revision ID: a14f9c203b71
Revises: 9c4e2a7b1d63
Create Date: 2026-10-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a14f9c203b71"
down_revision = "9c4e2a7b1d63"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "users",
    "categories",
    "products",
    "sales",
    "sale_items",
    "stock_movements",
    "restocks",
    "suppliers",
    "cashier_shifts",
    "purchase_orders",
    "purchase_order_items",
    "cash_movements",
    "sale_returns",
    "sale_return_items",
    "audit_logs",
)

BRANCH_TABLES = (
    "users",
    "products",
    "sales",
    "sale_items",
    "stock_movements",
    "restocks",
    "cashier_shifts",
    "purchase_orders",
    "purchase_order_items",
    "cash_movements",
    "sale_returns",
    "sale_return_items",
    "audit_logs",
)


def upgrade():
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KES"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Africa/Nairobi"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_status", "tenants", ["status"])

    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_branches_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_branches_tenant_id_id"),
    )
    op.create_index("ix_branches_tenant_id", "branches", ["tenant_id"])

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, currency, timezone, status, created_at) "
            "VALUES (1, 'Existing POS Business', 'existing-pos-business', 'KES', "
            "'Africa/Nairobi', 'active', CURRENT_TIMESTAMP)"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO branches (id, tenant_id, name, is_default, is_active, created_at) "
            "VALUES (1, 1, 'Main Branch', TRUE, TRUE, CURRENT_TIMESTAMP)"
        )
    )
    connection.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('tenants', 'id'), "
        "(SELECT MAX(id) FROM tenants))"
    ))
    connection.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('branches', 'id'), "
        "(SELECT MAX(id) FROM branches))"
    ))

    for table_name in TENANT_TABLES:
        op.add_column(table_name, sa.Column("tenant_id", sa.Integer(), nullable=True))
        connection.execute(sa.text(f"UPDATE {table_name} SET tenant_id = 1"))

    for table_name in BRANCH_TABLES:
        op.add_column(table_name, sa.Column("branch_id", sa.Integer(), nullable=True))
        connection.execute(sa.text(f"UPDATE {table_name} SET branch_id = 1"))

    for table_name in TENANT_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_foreign_key(
                f"fk_{table_name}_tenant_id_tenants",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_index(f"ix_{table_name}_tenant_id", ["tenant_id"])

    for table_name in BRANCH_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("branch_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_foreign_key(
                f"fk_{table_name}_branch_id_branches",
                "branches",
                ["branch_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_foreign_key(
                f"fk_{table_name}_tenant_branch",
                "branches",
                ["tenant_id", "branch_id"],
                ["tenant_id", "id"],
                ondelete="RESTRICT",
            )
            batch_op.create_index(f"ix_{table_name}_branch_id", ["branch_id"])

    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_constraint("categories_name_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_categories_tenant_name", ["tenant_id", "name"]
        )

    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.drop_constraint("uq_suppliers_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_suppliers_tenant_name", ["tenant_id", "name"]
        )

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_barcode")
        batch_op.create_index("ix_products_barcode", ["barcode"], unique=False)
        batch_op.create_unique_constraint(
            "uq_products_branch_barcode", ["branch_id", "barcode"]
        )

    with op.batch_alter_table("sales") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("idempotency_hash", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            "uq_sales_branch_idempotency_key", ["branch_id", "idempotency_key"]
        )

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.alter_column("currency", server_default=None)
        batch_op.alter_column("timezone", server_default=None)
        batch_op.alter_column("status", server_default=None)
    with op.batch_alter_table("branches") as batch_op:
        batch_op.alter_column("is_default", server_default=None)
        batch_op.alter_column("is_active", server_default=None)


def downgrade():
    with op.batch_alter_table("sales") as batch_op:
        batch_op.drop_constraint("uq_sales_branch_idempotency_key", type_="unique")
        batch_op.drop_column("idempotency_hash")
        batch_op.drop_column("idempotency_key")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("uq_products_branch_barcode", type_="unique")
        batch_op.drop_index("ix_products_barcode")
        batch_op.create_index("ix_products_barcode", ["barcode"], unique=True)

    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.drop_constraint("uq_suppliers_tenant_name", type_="unique")
        batch_op.create_unique_constraint("uq_suppliers_name", ["name"])

    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_constraint("uq_categories_tenant_name", type_="unique")
        batch_op.create_unique_constraint("categories_name_key", ["name"])

    for table_name in reversed(BRANCH_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(f"fk_{table_name}_tenant_branch", type_="foreignkey")
            batch_op.drop_constraint(f"fk_{table_name}_branch_id_branches", type_="foreignkey")
            batch_op.drop_index(f"ix_{table_name}_branch_id")
            batch_op.drop_column("branch_id")

    for table_name in reversed(TENANT_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(f"fk_{table_name}_tenant_id_tenants", type_="foreignkey")
            batch_op.drop_index(f"ix_{table_name}_tenant_id")
            batch_op.drop_column("tenant_id")

    op.drop_index("ix_branches_tenant_id", table_name="branches")
    op.drop_table("branches")
    op.drop_index("ix_tenants_status", table_name="tenants")
    op.drop_table("tenants")
