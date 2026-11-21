"""Cadastros configuráveis: categorias, serviços e preferências do estúdio."""
from app.extensions import db
from app.models.base import TimestampMixin, enum_column
from app.models.enums import CategoryKind


class Category(TimestampMixin, db.Model):
    """Categorias financeiras (receita/despesa) e de estoque."""
    __tablename__ = "categories"
    __table_args__ = (db.UniqueConstraint("kind", "name", name="uq_category_kind_name"),)

    id = db.Column(db.Integer, primary_key=True)
    kind = enum_column(CategoryKind)
    name = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Service(TimestampMixin, db.Model):
    """Serviços oferecidos (ex.: sessão, retoque, flash day)."""
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    default_duration_minutes = db.Column(db.Integer, nullable=False, default=120)
    default_price_cents = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class StudioSetting(db.Model):
    """Configurações chave/valor (nome do estúdio, contato, preferências)."""
    __tablename__ = "studio_settings"

    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text, nullable=True)
