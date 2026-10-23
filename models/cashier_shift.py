from datetime import datetime, timezone
from decimal import Decimal

from extensions import db
from models.tenant_scope import BranchScoped


class CashierShift(BranchScoped, db.Model):
    __tablename__ = "cashier_shifts"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_cashier_shifts_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    opening_cash = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0.0000"))
    closing_cash = db.Column(db.Numeric(12, 4))
    expected_cash = db.Column(db.Numeric(12, 4))
    cash_variance = db.Column(db.Numeric(12, 4))
    opened_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="cashier_shifts")
    sales = db.relationship("Sale", back_populates="shift")
    cash_movements = db.relationship("CashMovement", back_populates="shift")
    returns = db.relationship("SaleReturn", back_populates="shift")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "cashier": self.user.name if self.user else None,
            "status": self.status,
            "opening_cash": str(self.opening_cash),
            "closing_cash": str(self.closing_cash) if self.closing_cash is not None else None,
            "expected_cash": str(self.expected_cash) if self.expected_cash is not None else None,
            "cash_variance": str(self.cash_variance) if self.cash_variance is not None else None,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "cash_movements": [movement.to_dict() for movement in self.cash_movements],
        }
