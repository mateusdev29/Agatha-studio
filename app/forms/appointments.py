from datetime import datetime

from flask_wtf import FlaskForm
from app.forms.fields import SelectField
from wtforms import DateField, IntegerField, StringField, TextAreaField, TimeField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.extensions import db
from app.forms.choices import client_choices
from app.forms.fields import MoneyField
from app.models import Project
from app.models.enums import PaymentMethod, ProjectStatus, TransactionStatus


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class _WhenMixin:
    """Data + horário + duração, comuns a criar, editar e remarcar."""
    date = DateField("Data", format="%Y-%m-%d", validators=[DataRequired(message="Informe a data.")])
    time = TimeField("Horário", format="%H:%M", validators=[DataRequired(message="Informe o horário.")])
    duration_minutes = IntegerField("Duração (minutos)", default=120,
                                    validators=[DataRequired(message="Informe a duração."),
                                                NumberRange(min=15, max=720, message="Use de 15 a 720 minutos.")])

    def validate_date(self, field):
        if field.data and not (2000 <= field.data.year <= 2100):
            raise ValidationError("Data inválida.")

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.date.data, self.time.data)


class RescheduleForm(_WhenMixin, FlaskForm):
    pass


class AppointmentForm(_WhenMixin, FlaskForm):
    client_id = SelectField("Cliente", coerce=int, validate_choice=True)
    project_id = SelectField("Projeto", coerce=int, validate_choice=True)
    service = StringField("Serviço", filters=[_strip], validators=[Optional(), Length(max=100)])
    price_cents = MoneyField("Valor (R$)")
    deposit_cents = MoneyField("Sinal (R$)")
    notes = TextAreaField("Observações", filters=[_strip], validators=[Optional(), Length(max=3000)])

    def __init__(self, *args, current_client_id=None, current_project_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_id.choices = client_choices(current_client_id)
        # Projetos em aberto de todos os clientes; o JS mostra só os do cliente escolhido (data-group).
        projects = (Project.query.filter(Project.status.notin_([ProjectStatus.DONE, ProjectStatus.CANCELED]))
                    .order_by(Project.name).all())
        if current_project_id and all(p.id != current_project_id for p in projects):
            current = db.session.get(Project, current_project_id)
            if current:
                projects.append(current)
        self.project_id.choices = [(0, "Sem projeto", {})] + [
            (p.id, f"{p.name} ({p.client.name})", {"data-group": str(p.client_id)}) for p in projects]

    def validate_project_id(self, field):
        if field.data:
            project = db.session.get(Project, field.data)
            if project and project.client_id != self.client_id.data:
                raise ValidationError("O projeto não pertence ao cliente escolhido.")

    def validate_deposit_cents(self, field):
        price = self.price_cents.data or 0
        if field.data and price and field.data > price:
            raise ValidationError("O sinal não pode ser maior que o valor.")

    def validate_price_cents(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("O valor não pode ser negativo.")

    def cleaned(self) -> dict:
        d = self.data
        return {
            "client_id": d["client_id"], "project_id": d.get("project_id") or None,
            "starts_at": self.starts_at, "duration_minutes": d["duration_minutes"],
            "service": d.get("service") or None, "price_cents": d.get("price_cents") or 0,
            "deposit_cents": d.get("deposit_cents") or 0, "notes": d.get("notes") or None,
        }


class DepositForm(FlaskForm):
    """Lançar o sinal do atendimento no Financeiro."""
    payment_method = SelectField("Forma de pagamento", choices=[("", "Não informada")] + PaymentMethod.choices(), validate_choice=True)
    date = DateField("Data", format="%Y-%m-%d", validators=[DataRequired(message="Informe a data.")])
    status = SelectField("Situação", choices=[(TransactionStatus.PAID.value, "Recebido"), (TransactionStatus.PENDING.value, "A receber")], validate_choice=True)

    def validate_date(self, field):
        if field.data and not (2000 <= field.data.year <= 2100):
            raise ValidationError("Data inválida.")
