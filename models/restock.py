from datetime import datetime, timezone
from extensions import db
from models.tenant_scope import BranchScoped


class Restock(BranchScoped, db.Model):
    __tablename__ = "restocks"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_restocks_quantity_positive"),
        db.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_restocks_unit_cost_nonnegative",
        ),
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"],
            name="fk_restocks_tenant_branch", ondelete="RESTRICT",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)
    supplier = db.Column(db.String(120), nullable=True)
    invoice_number = db.Column(db.String(60), nullable=True)
    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    product = db.relationship("Product", back_populates="restocks")
    supplier_record = db.relationship("Supplier", back_populates="restocks")
    user = db.relationship("User", back_populates="restocks")
    stock_movement = db.relationship(
        "StockMovement",
        back_populates="restock",
        uselist=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "supplier_id": self.supplier_id,
            "user_id": self.user_id,
            "quantity": self.quantity,
            "unit_cost": str(self.unit_cost) if self.unit_cost is not None else None,
            "supplier": self.supplier,
            "invoice_number": self.invoice_number,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }
