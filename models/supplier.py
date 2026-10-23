from datetime import datetime, timezone
from sqlalchemy import true

from extensions import db
from models.tenant_scope import TenantScoped


class Supplier(TenantScoped, db.Model):
    __tablename__ = "suppliers"
    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_suppliers_tenant_name"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    contact_name = db.Column(db.String(120))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(160))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=true())
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    restocks = db.relationship("Restock", back_populates="supplier_record")
    purchase_orders = db.relationship("PurchaseOrder", back_populates="supplier")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "contact_name": self.contact_name,
            "phone": self.phone,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }
