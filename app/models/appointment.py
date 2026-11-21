from datetime import timedelta

from app.extensions import db
from app.models.base import TimestampMixin, enum_column
from app.models.enums import AppointmentStatus


class Appointment(TimestampMixin, db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("project_sessions.id"))
    # Horário LOCAL do estúdio (sem fuso), como aparece na agenda.
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=120)
    service = db.Column(db.String(100))
    price_cents = db.Column(db.Integer, nullable=False, default=0)
    deposit_cents = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    status = enum_column(AppointmentStatus, default=AppointmentStatus.WAITING)

    client = db.relationship("Client", back_populates="appointments")
    project = db.relationship("Project", back_populates="appointments")
    session = db.relationship("ProjectSession")
    evaluation = db.relationship("Evaluation", back_populates="appointment", uselist=False)
    transactions = db.relationship("FinancialTransaction", back_populates="appointment")

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.duration_minutes)
