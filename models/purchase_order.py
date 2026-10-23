from datetime import datetime, timezone
from decimal import Decimal

from extensions import db
from models.tenant_scope import BranchScoped


class PurchaseOrder(BranchScoped, db.Model):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_purchase_orders_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="ordered", index=True)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    supplier = db.relationship("Supplier", back_populates="purchase_orders")
    items = db.relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier.name if self.supplier else None,
            "created_by_id": self.created_by_id,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "items": [item.to_dict() for item in self.items],
        }


class PurchaseOrderItem(BranchScoped, db.Model):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_purchase_order_items_quantity_positive"),
        db.CheckConstraint("received_quantity >= 0", name="ck_purchase_order_items_received_nonnegative"),
        db.CheckConstraint("received_quantity <= quantity", name="ck_purchase_order_items_received_lte_ordered"),
        db.CheckConstraint("unit_cost >= 0", name="ck_purchase_order_items_unit_cost_nonnegative"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_purchase_order_items_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    received_quantity = db.Column(db.Integer, nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=False)

    purchase_order = db.relationship("PurchaseOrder", back_populates="items")
    product = db.relationship("Product")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_title": self.product.title if self.product else None,
            "quantity": self.quantity,
            "received_quantity": self.received_quantity,
            "unit_cost": str(self.unit_cost if self.unit_cost is not None else Decimal("0.00")),
        }
