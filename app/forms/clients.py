import re
from datetime import date

from flask_wtf import FlaskForm
from app.forms.fields import SelectField
from wtforms import DateField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

SOURCE_CHOICES = [
    ("", "Não informado"), ("Instagram", "Instagram"), ("Indicação", "Indicação"),
    ("WhatsApp", "WhatsApp"), ("Site", "Site"), ("Passou no estúdio", "Passou no estúdio"), ("Outro", "Outro"),
]
SOURCE_VALUES = [v for v, _ in SOURCE_CHOICES if v]
_PHONE_CHARS = re.compile(r"^[0-9\s()+\-.]+$")
_INSTAGRAM = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class ClientForm(FlaskForm):
    name = StringField("Nome", filters=[_strip],
                       validators=[DataRequired(message="Informe o nome."), Length(max=150)])
    phone = StringField("Telefone / WhatsApp", filters=[_strip], validators=[Optional(), Length(max=30)])
    email = StringField("E-mail", filters=[_strip], validators=[Optional(), Email(message="E-mail inválido."), Length(max=254)])
    instagram = StringField("Instagram", filters=[_strip], validators=[Optional(), Length(max=31)])
    birth_date = DateField("Data de nascimento", format="%Y-%m-%d", validators=[Optional()])
    source = SelectField("Como conheceu o estúdio", choices=SOURCE_CHOICES, validate_choice=True)
    notes = TextAreaField("Observações", filters=[_strip], validators=[Optional(), Length(max=5000)])

    def validate_phone(self, field):
        if not field.data:
            return
        if not _PHONE_CHARS.match(field.data) or len(re.sub(r"[^0-9]", "", field.data)) < 8:
            raise ValidationError("Telefone inválido. Use DDD + número.")

    def validate_instagram(self, field):
        if field.data and not _INSTAGRAM.match(field.data.lstrip("@")):
            raise ValidationError("Usuário inválido. Use letras, números, ponto ou _.")

    def validate_birth_date(self, field):
        if field.data and not (date(1900, 1, 1) <= field.data <= date.today()):
            raise ValidationError("Data de nascimento inválida.")

    def cleaned(self) -> dict:
        """Dados prontos para o banco: vazio vira None, e-mail minúsculo, @ removido."""
        d = self.data
        return {
            "name": d["name"],
            "phone": d.get("phone") or None,
            "email": (d.get("email") or "").lower() or None,
            "instagram": (d.get("instagram") or "").lstrip("@") or None,
            "birth_date": d.get("birth_date"),
            "source": d.get("source") or None,
            "notes": d.get("notes") or None,
        }
