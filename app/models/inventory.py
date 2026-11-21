from app.extensions import db
from app.models.base import TimestampMixin, enum_column, utcnow
from app.models.enums import MovementType


class InventoryItem(TimestampMixin, db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    quantity = db.Column(db.Integer, nullable=False, default=0)
    unit = db.Column(db.String(20), nullable=False, default="un")
    min_quantity = db.Column(db.Integer, nullable=False, default=0)
    cost_cents = db.Column(db.Integer, nullable=False, default=0)
    supplier = db.Column(db.String(120))
    expires_on = db.Column(db.Date)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    category = db.relationship("Category")
    movements = db.relationship(
        "InventoryMovement", back_populates="item", order_by="InventoryMovement.created_at.desc()"
    )

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.min_quantity


class InventoryMovement(db.Model):
    """Histórico imutável. `delta` é sinalizado; `balance_after` é o saldo resultante."""
    __tablename__ = "inventory_movements"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    type = enum_column(MovementType)
    delta = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    item = db.relationship("InventoryItem", back_populates="movements")
    user = db.relationship("User")
