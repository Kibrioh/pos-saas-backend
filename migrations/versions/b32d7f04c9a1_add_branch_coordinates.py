"""add coordinates to branches

Revision ID: b32d7f04c9a1
Revises: a14f9c203b71
Create Date: 2026-10-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b32d7f04c9a1"
down_revision = "a14f9c203b71"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(sa.Column("latitude", sa.Numeric(10, 7), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Numeric(10, 7), nullable=True))
        batch_op.create_check_constraint(
            "ck_branches_latitude_range",
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
        )
        batch_op.create_check_constraint(
            "ck_branches_longitude_range",
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
        )
        batch_op.create_check_constraint(
            "ck_branches_coordinate_pair",
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
        )


def downgrade():
    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_constraint("ck_branches_coordinate_pair", type_="check")
        batch_op.drop_constraint("ck_branches_longitude_range", type_="check")
        batch_op.drop_constraint("ck_branches_latitude_range", type_="check")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
