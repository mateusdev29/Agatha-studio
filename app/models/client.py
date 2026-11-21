from app.extensions import db
from app.models.base import TimestampMixin


class Client(TimestampMixin, db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(254))
    instagram = db.Column(db.String(60))
    birth_date = db.Column(db.Date)
    source = db.Column(db.String(60))  # origem do cliente (Instagram, indicação...)
    notes = db.Column(db.Text)
    archived_at = db.Column(db.DateTime, nullable=True)  # arquivar em vez de excluir

    projects = db.relationship("Project", back_populates="client", lazy="dynamic")
    appointments = db.relationship("Appointment", back_populates="client", lazy="dynamic")
    quotes = db.relationship("Quote", back_populates="client", lazy="dynamic")
    anamnesis_responses = db.relationship("AnamnesisResponse", back_populates="client", lazy="dynamic")
    evaluations = db.relationship("Evaluation", back_populates="client", lazy="dynamic")
    transactions = db.relationship("FinancialTransaction", back_populates="client", lazy="dynamic")

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
