"""Contadores temporários de falhas por combinação de IP e navegador (somente hash)."""
from app.extensions import db
from app.models.base import utcnow


class LoginThrottle(db.Model):
    __tablename__ = "login_throttles"

    key_hash = db.Column(db.String(64), primary_key=True)
    failure_count = db.Column(db.Integer, nullable=False, default=0)
    window_started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    blocked_until = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, index=True)
