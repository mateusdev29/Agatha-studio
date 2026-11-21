"""Utilidades compartilhadas pelos modelos."""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.extensions import db


def utcnow():
    """UTC "ingênuo" (sem tzinfo): SQLite não guarda fuso."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enum_column(enum_cls, default=None, nullable=False):
    """Coluna Enum gravando o *valor* (ex.: 'em_andamento') como texto."""
    return db.Column(
        sa.Enum(
            enum_cls,
            native_enum=False,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
            length=32,
        ),
        default=default,
        nullable=nullable,
    )


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
