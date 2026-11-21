from app.extensions import db
from app.models.base import utcnow


class ActivityLog(db.Model):
    """Registro de atividades para 'atividades recentes' e auditoria simples."""
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(40), nullable=False)       # ex.: login, created, updated
    entity_type = db.Column(db.String(40))                  # ex.: client, quote
    entity_id = db.Column(db.Integer)
    description = db.Column(db.String(250), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship("User")
