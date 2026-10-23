from datetime import datetime, timezone
from decimal import Decimal
from extensions import db
from models.tenant_scope import BranchScoped

class Sale(BranchScoped, db.Model):
    __tablename__ = "sales"
    __table_args__ = (
        db.CheckConstraint("total_amount >= 0", name="ck_sales_total_nonnegative"),
        db.CheckConstraint(
            "amount_tendered IS NULL OR amount_tendered >= 0",
            name="ck_sales_tendered_nonnegative",
        ),
        db.CheckConstraint("change_given >= 0", name="ck_sales_change_nonnegative"),
        db.UniqueConstraint("branch_id", "idempotency_key", name="uq_sales_branch_idempotency_key"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_sales_tenant_branch", ondelete="RESTRICT",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    total_amount = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0.0000"))
    payment_method = db.Column(db.String(30), nullable=False, default="cash")
    amount_tendered = db.Column(db.Numeric(12, 4))
    change_given = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0.0000"))
    idempotency_key = db.Column(db.String(80))
    idempotency_hash = db.Column(db.String(64))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    user = db.relationship("User", back_populates="sales")
    shift = db.relationship("CashierShift", back_populates="sales")
    items = db.relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    returns = db.relationship("SaleReturn", back_populates="sale")

    def to_dict(self):
        return {"id": self.id, "tenant_id": self.tenant_id, "branch_id": self.branch_id,
                "user_id": self.user_id, "total_amount": str(self.total_amount),
                "shift_id": self.shift_id, "payment_method": self.payment_method,
                "amount_tendered": str(self.amount_tendered) if self.amount_tendered is not None else None,
                "change_given": str(self.change_given or Decimal("0.0000")),
                "created_at": self.created_at.isoformat(),
                "returns": [return_record.to_dict() for return_record in self.returns],
                "items": [item.to_dict() for item in self.items]}
