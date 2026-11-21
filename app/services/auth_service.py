"""Regras de autenticação (sem dependência de request/response)."""
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User
from app.models.base import utcnow
from app.services.activity_service import log_activity

# Hash "isca": mantém o tempo de resposta parecido quando o e-mail não existe.
_DUMMY_HASH = generate_password_hash("timing-equalizer")


class AuthResult:
    def __init__(self, user=None, error=None):
        self.user = user
        self.error = error

    @property
    def ok(self):
        return self.user is not None


GENERIC_ERROR = "E-mail ou senha incorretos."
LOCKED_ERROR = "Muitas tentativas. Tente novamente em alguns minutos."


def authenticate(email: str, password: str) -> AuthResult:
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None:
        check_password_hash(_DUMMY_HASH, password or "")
        return AuthResult(error=GENERIC_ERROR)

    if user.is_locked:
        return AuthResult(error=LOCKED_ERROR)

    if not user.is_active or not user.check_password(password or ""):
        _register_failure(user)
        return AuthResult(error=GENERIC_ERROR)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    log_activity("login", "Login realizado", user=user, entity_type="user", entity_id=user.id)
    db.session.commit()
    return AuthResult(user=user)


def _register_failure(user: User) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= current_app.config["MAX_FAILED_LOGINS"]:
        user.locked_until = utcnow() + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
        user.failed_login_count = 0
    db.session.commit()
