"""Regras de autenticação (sem dependência de request/response)."""
import hashlib
import hmac
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import LoginThrottle, User
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


def authenticate(email: str, password: str, ip_address: str | None = None,
                 user_agent: str | None = None) -> AuthResult:
    device_key = _device_key(ip_address, user_agent)
    if _device_is_locked(device_key):
        return AuthResult(error=LOCKED_ERROR)

    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None:
        check_password_hash(_DUMMY_HASH, password or "")
        _register_device_failure(device_key)
        return AuthResult(error=GENERIC_ERROR)

    if user.is_locked:
        _register_device_failure(device_key)
        return AuthResult(error=LOCKED_ERROR)

    if not user.is_active or not user.check_password(password or ""):
        _register_failure(user)
        _register_device_failure(device_key)
        return AuthResult(error=GENERIC_ERROR)

    _clear_device_failures(device_key)
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


def _device_key(ip_address: str | None, user_agent: str | None) -> str:
    """HMAC para não guardar IP nem User-Agent em texto no banco."""
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    identity = f"{ip_address or 'unknown'}\0{(user_agent or '')[:512]}".encode("utf-8", "replace")
    return hmac.new(secret, identity, hashlib.sha256).hexdigest()


def _device_is_locked(key: str) -> bool:
    now = utcnow()
    window = timedelta(minutes=current_app.config["DEVICE_LOGIN_WINDOW_MINUTES"])
    # Remove hashes expirados para que o armazenamento não cresça indefinidamente.
    LoginThrottle.query.filter(LoginThrottle.updated_at < now - window * 2).delete(synchronize_session=False)
    entry = db.session.get(LoginThrottle, key)
    if entry is None:
        db.session.commit()
        return False
    if entry.blocked_until and entry.blocked_until > now:
        db.session.commit()
        return True
    if entry.window_started_at + window <= now:
        db.session.delete(entry)
    db.session.commit()
    return False


def _register_device_failure(key: str) -> None:
    now = utcnow()
    entry = db.session.get(LoginThrottle, key)
    window = timedelta(minutes=current_app.config["DEVICE_LOGIN_WINDOW_MINUTES"])
    if entry is None or entry.window_started_at + window <= now:
        if entry is not None:
            db.session.delete(entry)
            db.session.flush()
        entry = LoginThrottle(key_hash=key, failure_count=0, window_started_at=now)
        db.session.add(entry)
    entry.failure_count += 1
    entry.updated_at = now
    if entry.failure_count >= current_app.config["MAX_DEVICE_FAILED_LOGINS"]:
        entry.blocked_until = now + timedelta(minutes=current_app.config["DEVICE_LOCKOUT_MINUTES"])
    db.session.commit()


def _clear_device_failures(key: str) -> None:
    entry = db.session.get(LoginThrottle, key)
    if entry is not None:
        db.session.delete(entry)
