from flask_wtf import FlaskForm
from app.forms.fields import SelectField
from wtforms import DateField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.extensions import db
from app.forms.choices import client_choices
from app.forms.fields import MoneyField
from app.models import Category, Client, Project
from app.models.enums import CategoryKind, PaymentMethod, TransactionStatus, TransactionType


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class TransactionForm(FlaskForm):
    description = StringField("Descrição", filters=[_strip], validators=[DataRequired(message="Informe a descrição."), Length(max=200)])
    category_id = SelectField("Categoria", coerce=int, validate_choice=True)
    amount_cents = MoneyField("Valor (R$)")
    date = DateField("Data", format="%Y-%m-%d", validators=[DataRequired(message="Informe a data.")])
    payment_method = SelectField("Forma de pagamento", choices=[("", "Não informada")] + PaymentMethod.choices(), validate_choice=True)
    status = SelectField("Situação", choices=TransactionStatus.choices(), default=TransactionStatus.PAID.value)
    client_id = SelectField("Cliente", coerce=int, validate_choice=True)
    project_id = SelectField("Projeto", coerce=int, validate_choice=True)
    supplier = StringField("Fornecedor", filters=[_strip], validators=[Optional(), Length(max=120)])
    notes = TextAreaField("Observações", filters=[_strip], validators=[Optional(), Length(max=3000)])

    def __init__(self, *args, kind: TransactionType, current=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        ck = CategoryKind.INCOME if kind == TransactionType.INCOME else CategoryKind.EXPENSE
        cats = Category.query.filter_by(kind=ck, is_active=True).order_by(Category.name).all()
        if current and current.category and current.category not in cats:
            cats.append(current.category)
        self.category_id.choices = [(0, "Sem categoria")] + [(c.id, c.name) for c in cats]
        if kind == TransactionType.EXPENSE:
            # Cliente e projeto não se aplicam a despesas e a tela não os exibe. Se ficassem no formulário, a
            # validação falharia em campos invisíveis e a despesa seria recusada sem nenhuma mensagem.
            del self.client_id, self.project_id
            return
        self.client_id.choices = [(0, "Sem cliente")] + client_choices(current.client_id if current else None)
        projects = Project.query.order_by(Project.name).all()
        self.project_id.choices = [(0, "Sem projeto", {})] + [
            (p.id, f"{p.name} ({p.client.name})", {"data-group": str(p.client_id)}) for p in projects]

    def validate_amount_cents(self, field):
        if not field.data or field.data <= 0:
            raise ValidationError("Informe um valor maior que zero.")

    def validate_date(self, field):
        if field.data and not (2000 <= field.data.year <= 2100):
            raise ValidationError("Data inválida.")

    def validate_project_id(self, field):
        if field.data and self.client_id.data:
            project = db.session.get(Project, field.data)
            if project and project.client_id != self.client_id.data:
                raise ValidationError("O projeto não pertence ao cliente escolhido.")

    def cleaned(self) -> dict:
        d = self.data
        client_id, project_id = d.get("client_id") or None, d.get("project_id") or None
        if project_id and not client_id:                       # deduz o cliente pelo projeto
            client_id = db.session.get(Project, project_id).client_id
        income = self.kind == TransactionType.INCOME
        return {"type": self.kind, "description": d["description"], "category_id": d.get("category_id") or None,
                "amount_cents": d["amount_cents"], "date": d["date"],
                "payment_method": PaymentMethod(d["payment_method"]) if d.get("payment_method") else None,
                "status": TransactionStatus(d["status"]), "client_id": client_id if income else None,
                "project_id": project_id if income else None,
                "supplier": (d.get("supplier") or None) if not income else None, "notes": d.get("notes") or None}
