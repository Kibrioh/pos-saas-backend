from datetime import datetime, timezone
from extensions import db
from models.tenant_scope import BranchScoped

class StockMovement(BranchScoped, db.Model):
    __tablename__ = "stock_movements"
    __table_args__ = (
        db.CheckConstraint("quantity_delta <> 0", name="ck_stock_movements_nonzero_delta"),
        db.CheckConstraint("stock_before >= 0", name="ck_stock_movements_before_nonnegative"),
        db.CheckConstraint("stock_after >= 0", name="ck_stock_movements_after_nonnegative"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_stock_movements_tenant_branch", ondelete="RESTRICT",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    movement_type = db.Column(db.String(30), nullable=False)
    quantity_delta = db.Column(db.Integer, nullable=False)
    stock_before = db.Column(db.Integer, nullable=False)
    stock_after = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    product = db.relationship("Product", back_populates="stock_movements")
    user = db.relationship("User", back_populates="stock_movements")
    restock_id = db.Column(
        db.Integer,
        db.ForeignKey("restocks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    restock = db.relationship("Restock", back_populates="stock_movement")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "movement_type": self.movement_type,
            "quantity_delta": self.quantity_delta,
            "stock_before": self.stock_before,
            "stock_after": self.stock_after,
            "restock_id": self.restock_id,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }
