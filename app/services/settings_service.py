"""Configurações do estúdio (chave/valor) e preferências do sistema, com padrões vindos do config."""
from flask import current_app

from app.extensions import db
from app.models import StudioSetting

DEFAULT_DURATION = 120


def get_setting(key: str, default=None):
    row = db.session.get(StudioSetting, key)
    return row.value if row and row.value not in (None, "") else default


def set_setting(key: str, value) -> None:
    row = db.session.get(StudioSetting, key)
    value = None if value in (None, "") else str(value)
    if row:
        row.value = value
    else:
        db.session.add(StudioSetting(key=key, value=value))


def get_int(key: str, default: int) -> int:
    try:
        return int(get_setting(key, default))
    except (TypeError, ValueError):
        return default


def studio_name() -> str:
    return get_setting("studio_name", current_app.config["STUDIO_NAME"])


def quote_validity_days() -> int:
    return get_int("pref_quote_validity_days", current_app.config["QUOTE_VALIDITY_DAYS"])


def default_duration() -> int:
    return get_int("pref_default_duration", DEFAULT_DURATION)
