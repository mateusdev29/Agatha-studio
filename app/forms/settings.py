from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, ValidationError

from app.forms.fields import MoneyField
from app.models import User


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class ProfileForm(FlaskForm):
    name = StringField("Nome", filters=[_strip], validators=[DataRequired(message="Informe o nome."), Length(max=120)])
    email = StringField("E-mail", filters=[_strip], validators=[DataRequired(message="Informe o e-mail."), Email(message="E-mail inválido."), Length(max=254)])

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def validate_email(self, field):
        other = User.query.filter(User.email == field.data.lower(), User.id != self.user.id).first()
        if other:
            raise ValidationError("Este e-mail já está em uso.")


class PasswordForm(FlaskForm):
    current = PasswordField("Senha atual", validators=[DataRequired(message="Informe a senha atual.")])
    new = PasswordField("Nova senha", validators=[DataRequired(message="Informe a nova senha."), Length(min=10, max=128, message="Use de 10 a 128 caracteres.")])
    confirm = PasswordField("Confirmar nova senha", validators=[EqualTo("new", message="As senhas não coincidem.")])

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def validate_current(self, field):
        if not self.user.check_password(field.data or ""):
            raise ValidationError("Senha atual incorreta.")


class StudioForm(FlaskForm):
    studio_name = StringField("Nome do estúdio", filters=[_strip], validators=[DataRequired(message="Informe o nome."), Length(max=120)])
    studio_phone = StringField("Telefone / WhatsApp", filters=[_strip], validators=[Optional(), Length(max=30)])
    studio_instagram = StringField("Instagram", filters=[_strip], validators=[Optional(), Length(max=60)])
    studio_address = StringField("Endereço", filters=[_strip], validators=[Optional(), Length(max=250)])


class PreferencesForm(FlaskForm):
    pref_quote_validity_days = IntegerField("Validade padrão dos orçamentos (dias)", validators=[DataRequired(message="Informe os dias."), NumberRange(min=1, max=365, message="Use de 1 a 365 dias.")])
    pref_default_duration = IntegerField("Duração padrão dos atendimentos (minutos)", validators=[DataRequired(message="Informe a duração."), NumberRange(min=15, max=720, message="Use de 15 a 720 minutos.")])


class ServiceForm(FlaskForm):
    name = StringField("Serviço", filters=[_strip], validators=[DataRequired(message="Informe o nome."), Length(max=100)])
    default_duration_minutes = IntegerField("Duração padrão (minutos)", default=120, validators=[DataRequired(message="Informe a duração."), NumberRange(min=15, max=720, message="Use de 15 a 720 minutos.")])
    default_price_cents = MoneyField("Valor padrão (R$)")
    is_active = BooleanField("Ativo", default=True)


class CategoryForm(FlaskForm):
    name = StringField("Nome", filters=[_strip], validators=[DataRequired(message="Informe o nome."), Length(max=80)])
    kind = SelectField("Tipo", choices=[("receita", "Receita"), ("despesa", "Despesa")], validate_choice=True)
    is_active = BooleanField("Ativa", default=True)
