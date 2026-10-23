from sqlalchemy.orm import declared_attr

from extensions import db


class TenantScoped:
    @declared_attr
    def tenant_id(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class BranchScoped(TenantScoped):
    @declared_attr
    def branch_id(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
