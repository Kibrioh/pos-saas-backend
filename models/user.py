from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models.tenant_scope import TenantScoped
from utils.password_policy import password_policy_error

class User(TenantScoped, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name="fk_users_tenant_branch",
            ondelete="RESTRICT",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="cashier")
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    sales = db.relationship("Sale", back_populates="user")
    cashier_shifts = db.relationship("CashierShift", back_populates="user")
    stock_movements = db.relationship("StockMovement", back_populates="user")
    restocks = db.relationship("Restock", back_populates="user")

    def set_password(self, password):
        error = password_policy_error(password)
        if error:
            raise ValueError(error)
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "role": self.role,
            "tenant_id": self.tenant_id,
            "branch_id": self.branch_id,
            "created_at": self.created_at.isoformat(),
        }
