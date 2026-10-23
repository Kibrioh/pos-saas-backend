from datetime import datetime, timezone

from extensions import db
from models.tenant_scope import BranchScoped


class CashMovement(BranchScoped, db.Model):
    __tablename__ = "cash_movements"
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_cash_movements_amount_positive"),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_cash_movements_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Numeric(12, 4), nullable=False)
    note = db.Column(db.String(240), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    shift = db.relationship("CashierShift", back_populates="cash_movements")

    def to_dict(self):
        return {
            "id": self.id,
            "shift_id": self.shift_id,
            "user_id": self.user_id,
            "direction": self.direction,
            "amount": str(self.amount),
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }
