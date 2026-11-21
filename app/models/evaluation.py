from app.extensions import db
from app.models.base import TimestampMixin


class Evaluation(TimestampMixin, db.Model):
    """Avaliação de satisfação. Nota de 0 a 10 (permite média e cálculo de NPS)."""
    __tablename__ = "evaluations"
    __table_args__ = (db.CheckConstraint("score BETWEEN 0 AND 10", name="ck_evaluation_score_range"),)

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), unique=True)
    score = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    evaluated_on = db.Column(db.Date, nullable=False)

    client = db.relationship("Client", back_populates="evaluations")
    appointment = db.relationship("Appointment", back_populates="evaluation")
