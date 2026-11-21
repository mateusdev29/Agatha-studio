from app.extensions import db
from app.models.base import TimestampMixin, enum_column
from app.models.enums import FieldType


class AnamnesisTemplate(TimestampMixin, db.Model):
    """Pergunta configurável da ficha de anamnese."""
    __tablename__ = "anamnesis_templates"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(250), nullable=False)
    help_text = db.Column(db.String(250))
    field_type = enum_column(FieldType, default=FieldType.TEXT)
    options = db.Column(db.JSON)  # lista de opções (checkbox/radio/select)
    required = db.Column(db.Boolean, nullable=False, default=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class AnamnesisResponse(TimestampMixin, db.Model):
    """Ficha preenchida. `answers` guarda um snapshot (pergunta + resposta),
    para o histórico não mudar se a pergunta for editada depois.
    DADO SENSÍVEL de saúde: nunca usar em dashboards/gráficos."""
    __tablename__ = "anamnesis_responses"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    answers = db.Column(db.JSON, nullable=False, default=list)
    accepted = db.Column(db.Boolean, nullable=False, default=False)
    accepted_at = db.Column(db.DateTime)
    signature_name = db.Column(db.String(150))  # assinatura digitada
    # Estrutura para o futuro link seguro (guarda só o HASH do token)
    link_token_hash = db.Column(db.String(64), unique=True)
    link_expires_at = db.Column(db.DateTime)

    client = db.relationship("Client", back_populates="anamnesis_responses")
