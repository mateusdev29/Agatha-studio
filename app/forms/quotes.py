from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.forms.choices import STYLE_CHOICES, body_region_choices, client_choices
from app.forms.fields import MoneyField
from app.utils.dates import today_local


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class QuoteForm(FlaskForm):
    client_id = SelectField("Cliente", coerce=int, validate_choice=True)
    description = TextAreaField("Descrição da tatuagem", filters=[_strip],
                                validators=[DataRequired(message="Descreva a tatuagem."), Length(max=3000)])
    style = SelectField("Estilo", choices=STYLE_CHOICES, validate_choice=True)
    body_region_id = SelectField("Região do corpo", coerce=int, validate_choice=True)
    size = StringField("Tamanho", filters=[_strip], validators=[Optional(), Length(max=60)])
    price_cents = MoneyField("Valor (R$)")
    valid_until = DateField("Válido até", format="%Y-%m-%d", validators=[Optional()])
    notes = TextAreaField("Observações internas", filters=[_strip], validators=[Optional(), Length(max=3000)])

    def __init__(self, *args, current_client_id=None, original_valid_until=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_valid_until = original_valid_until
        self.client_id.choices = client_choices(current_client_id)
        self.body_region_id.choices = body_region_choices()

    def validate_price_cents(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("O valor não pode ser negativo.")

    def validate_valid_until(self, field):
        if not field.data:
            return
        if field.data.year > 2100:
            raise ValidationError("Data inválida.")
        # Datas passadas só são aceitas se já eram a validade gravada (edição sem mexer no campo).
        if field.data < today_local() and field.data != self._original_valid_until:
            raise ValidationError("A validade não pode estar no passado.")

    def cleaned(self) -> dict:
        d = self.data
        return {
            "client_id": d["client_id"], "description": d["description"],
            "style": d.get("style") or None, "body_region_id": d.get("body_region_id") or None,
            "size": d.get("size") or None, "price_cents": d.get("price_cents") or 0,
            "valid_until": d.get("valid_until"), "notes": d.get("notes") or None,
        }
