from datetime import datetime, timezone
from decimal import Decimal

from extensions import db
from models.tenant_scope import BranchScoped


class SaleReturn(BranchScoped, db.Model):
    __tablename__ = "sale_returns"
    __table_args__ = (
        db.CheckConstraint("refund_total >= 0", name="ck_sale_returns_total_nonnegative"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_sale_returns_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False, index=True)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = db.Column(db.String(240), nullable=False)
    refund_method = db.Column(db.String(30), nullable=False)
    refund_total = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0.0000"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    sale = db.relationship("Sale", back_populates="returns")
    processor = db.relationship("User")
    shift = db.relationship("CashierShift", back_populates="returns")
    items = db.relationship("SaleReturnItem", back_populates="sale_return", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "sale_id": self.sale_id,
            "processed_by_id": self.processed_by_id,
            "shift_id": self.shift_id,
            "reason": self.reason,
            "refund_method": self.refund_method,
            "refund_total": str(self.refund_total),
            "created_at": self.created_at.isoformat(),
            "items": [item.to_dict() for item in self.items],
        }


class SaleReturnItem(BranchScoped, db.Model):
    __tablename__ = "sale_return_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_sale_return_items_quantity_positive"),
        db.CheckConstraint("unit_price >= 0", name="ck_sale_return_items_price_nonnegative"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_sale_return_items_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_return_id = db.Column(db.Integer, db.ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 4), nullable=False)
    unit_cost = db.Column(db.Numeric(12, 4))
    restock = db.Column(db.Boolean, nullable=False, default=False)

    sale_return = db.relationship("SaleReturn", back_populates="items")
    sale_item = db.relationship("SaleItem")
    product = db.relationship("Product")

    def to_dict(self):
        return {
            "id": self.id,
            "sale_item_id": self.sale_item_id,
            "product_id": self.product_id,
            "product_title": self.product.title if self.product else None,
            "quantity": self.quantity,
            "unit_price": str(self.unit_price),
            "unit_cost": str(self.unit_cost) if self.unit_cost is not None else None,
            "restock": self.restock,
        }
