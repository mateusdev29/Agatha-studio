from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError

from app.forms.choices import client_choices
from app.models.enums import FieldType

CHOICE_TYPES = {FieldType.CHECKBOX.value, FieldType.RADIO.value, FieldType.SELECT.value}


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class QuestionForm(FlaskForm):
    label = StringField("Pergunta", filters=[_strip], validators=[DataRequired(message="Informe a pergunta."), Length(max=250)])
    help_text = StringField("Texto de apoio", filters=[_strip], validators=[Optional(), Length(max=250)])
    field_type = SelectField("Tipo de resposta", choices=FieldType.choices(), validate_choice=True)
    options_text = TextAreaField("Opções (uma por linha)", filters=[_strip], validators=[Optional(), Length(max=3000)])
    position = IntegerField("Ordem", default=0, validators=[InputRequired(message="Informe a ordem."), NumberRange(min=0, max=9999, message="Use de 0 a 9999.")])
    required = BooleanField("Resposta obrigatória")
    is_active = BooleanField("Ativa", default=True)

    def parsed_options(self):
        return [o.strip() for o in (self.options_text.data or "").splitlines() if o.strip()]

    def validate_options_text(self, field):
        if self.field_type.data in CHOICE_TYPES:
            opts = self.parsed_options()
            if len(opts) < 2:
                raise ValidationError("Informe ao menos 2 opções, uma por linha.")
            if len(opts) > 30 or any(len(o) > 100 for o in opts) or len(set(opts)) != len(opts):
                raise ValidationError("Use até 30 opções únicas de até 100 caracteres.")


class FillForm(FlaskForm):
    client_id = SelectField("Cliente", coerce=int, validate_choice=True)
    accepted = BooleanField("Declaro que as informações são verdadeiras e autorizo o procedimento.")
    signature_name = StringField("Assinatura (nome completo)", filters=[_strip], validators=[DataRequired(message="Digite seu nome completo para assinar."), Length(max=150)])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_id.choices = client_choices()

    def validate_accepted(self, field):
        if not field.data:
            raise ValidationError("É necessário aceitar o termo para registrar a ficha.")
