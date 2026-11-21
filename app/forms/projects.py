from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, IntegerField, MultipleFileField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.forms.choices import STYLE_CHOICES, body_region_choices, client_choices
from app.forms.fields import MoneyField
from app.models.enums import ProjectStatus, SessionStatus


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class ProjectForm(FlaskForm):
    client_id = SelectField("Cliente", coerce=int, validate_choice=True)
    name = StringField("Nome do projeto", filters=[_strip],
                       validators=[DataRequired(message="Informe o nome do projeto."), Length(max=150)])
    description = TextAreaField("Descrição", filters=[_strip], validators=[Optional(), Length(max=5000)])
    style = SelectField("Estilo", choices=STYLE_CHOICES, validate_choice=True)
    body_region_id = SelectField("Região do corpo", coerce=int, validate_choice=True)
    size = StringField("Tamanho", filters=[_strip], validators=[Optional(), Length(max=60)])
    price_cents = MoneyField("Valor (R$)")
    status = SelectField("Status", choices=ProjectStatus.choices(), default=ProjectStatus.QUOTE.value)
    notes = TextAreaField("Observações", filters=[_strip], validators=[Optional(), Length(max=5000)])

    def __init__(self, *args, current_client_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_id.choices = client_choices(current_client_id)
        self.body_region_id.choices = body_region_choices()

    def validate_price_cents(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("O valor não pode ser negativo.")

    def cleaned(self) -> dict:
        d = self.data
        return {
            "client_id": d["client_id"],
            "name": d["name"],
            "description": d.get("description") or None,
            "style": d.get("style") or None,
            "body_region_id": d.get("body_region_id") or None,
            "size": d.get("size") or None,
            "price_cents": d.get("price_cents") or 0,
            "status": ProjectStatus(d["status"]),
            "notes": d.get("notes") or None,
        }


class SessionForm(FlaskForm):
    scheduled_at = DateTimeLocalField("Data e horário", format="%Y-%m-%dT%H:%M",
                                      validators=[DataRequired(message="Informe a data e o horário.")])
    duration_minutes = IntegerField("Duração (minutos)", default=120,
                                    validators=[DataRequired(message="Informe a duração."),
                                                NumberRange(min=15, max=720, message="Use de 15 a 720 minutos.")])
    price_cents = MoneyField("Valor da sessão (R$)")
    status = SelectField("Status", choices=SessionStatus.choices(), default=SessionStatus.SCHEDULED.value)
    notes = TextAreaField("Observações", filters=[_strip], validators=[Optional(), Length(max=3000)])

    def validate_scheduled_at(self, field):
        if field.data and not (2000 <= field.data.year <= 2100):
            raise ValidationError("Data inválida.")

    def cleaned(self) -> dict:
        d = self.data
        return {
            "scheduled_at": d["scheduled_at"],
            "duration_minutes": d["duration_minutes"],
            "price_cents": d.get("price_cents") or 0,
            "status": SessionStatus(d["status"]),
            "notes": d.get("notes") or None,
        }


class ReferenceUploadForm(FlaskForm):
    """Só carrega o token CSRF e o campo de arquivos; a validação real está em upload_service."""
    files = MultipleFileField("Imagens de referência")
