from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import true
from extensions import db
from models.tenant_scope import BranchScoped

class Product(BranchScoped, db.Model):
    __tablename__ = "products"
    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_products_price_nonnegative"),
        db.CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),
        db.CheckConstraint("low_stock_threshold >= 0", name="ck_products_threshold_nonnegative"),
        db.UniqueConstraint("branch_id", "barcode", name="uq_products_branch_barcode"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_products_tenant_branch", ondelete="RESTRICT",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    brand = db.Column(db.String(120))
    barcode = db.Column(db.String(80), index=True)
    price = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0.0000"))
    unit_cost = db.Column(db.Numeric(12, 4))
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=5)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=true())
    thumbnail = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    category = db.relationship("Category", back_populates="products")
    sale_items = db.relationship("SaleItem", back_populates="product")
    stock_movements = db.relationship("StockMovement", back_populates="product")
    restocks = db.relationship("Restock", back_populates="product")

    def to_dict(self):
        return {"id": self.id, "tenant_id": self.tenant_id, "branch_id": self.branch_id,
                "category_id": self.category_id, "category": self.category.name if self.category else None,
                "title": self.title, "brand": self.brand, "price": str(self.price),
                "barcode": self.barcode,
                "unit_cost": str(self.unit_cost) if self.unit_cost is not None else None,
                "stock_quantity": self.stock_quantity, "low_stock_threshold": self.low_stock_threshold,
                "is_active": self.is_active,
                "thumbnail": self.thumbnail, "description": self.description,
                "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat()}
