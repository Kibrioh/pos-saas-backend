from datetime import datetime, timezone
from extensions import db
from models.tenant_scope import TenantScoped

class Category(TenantScoped, db.Model):
    __tablename__ = "categories"
    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_categories_tenant_name"),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    products = db.relationship("Product", back_populates="category")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "created_at": self.created_at.isoformat()}
