from datetime import datetime, timezone

from extensions import db


class Tenant(db.Model):
    __tablename__ = "tenants"
    __table_args__ = (db.UniqueConstraint("slug", name="uq_tenants_slug"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(100), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="KES")
    timezone = db.Column(db.String(64), nullable=False, default="Africa/Nairobi")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    branches = db.relationship("Branch", back_populates="tenant", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "currency": self.currency,
            "timezone": self.timezone,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class Branch(db.Model):
    __tablename__ = "branches"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_branches_tenant_name"),
        db.UniqueConstraint("tenant_id", "id", name="uq_branches_tenant_id_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", back_populates="branches")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "location": self.location,
            "is_default": self.is_default,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }
