"""store Google Place IDs for geocoded branches

Revision ID: d1f81ac4372b
Revises: b32d7f04c9a1
Create Date: 2026-10-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d1f81ac4372b"
down_revision = "b32d7f04c9a1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(sa.Column("google_place_id", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "ck_branches_google_place_id_without_coordinates",
            "google_place_id IS NULL OR (latitude IS NULL AND longitude IS NULL)",
        )


def downgrade():
    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_constraint("ck_branches_google_place_id_without_coordinates", type_="check")
        batch_op.drop_column("google_place_id")
