import sqlalchemy as sa

from app.extensions import db
from app.models.base import TimestampMixin, enum_column
from app.models.enums import PaymentMethod, TransactionStatus, TransactionType


class FinancialTransaction(TimestampMixin, db.Model):
    """Receita ou despesa. Valores em centavos, sempre positivos; o sinal vem do tipo."""
    __tablename__ = "financial_transactions"
    __table_args__ = (
        db.CheckConstraint("amount_cents >= 0", name="ck_transaction_amount_positive"),
        # Trava no banco: no máximo UM lançamento de sinal por atendimento (vale mesmo com duplo clique/concorrência).
        db.Index("uq_deposit_per_appointment", "appointment_id", unique=True, sqlite_where=sa.text("is_deposit = 1")),
    )

    id = db.Column(db.Integer, primary_key=True)
    type = enum_column(TransactionType)
    description = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    amount_cents = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    # Vínculo com a Agenda: usado pelo sinal lançado a partir de um atendimento.
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), index=True)
    is_deposit = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
    payment_method = enum_column(PaymentMethod, nullable=True)
    status = enum_column(TransactionStatus, default=TransactionStatus.PAID)
    supplier = db.Column(db.String(120))  # usado em despesas
    notes = db.Column(db.Text)

    category = db.relationship("Category")
    client = db.relationship("Client", back_populates="transactions")
    project = db.relationship("Project", back_populates="transactions")
    appointment = db.relationship("Appointment", back_populates="transactions")
