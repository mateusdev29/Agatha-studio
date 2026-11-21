from flask_wtf import FlaskForm
from app.forms.fields import SelectField
from wtforms import DateField, IntegerField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError

from app.forms.fields import MoneyField
from app.models import Category
from app.models.enums import CategoryKind, MovementType


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class ItemForm(FlaskForm):
    name = StringField("Produto", filters=[_strip], validators=[DataRequired(message="Informe o produto."), Length(max=150)])
    category_id = SelectField("Categoria", coerce=int, validate_choice=True)
    quantity = IntegerField("Quantidade inicial", default=0, validators=[Optional(), NumberRange(min=0, max=1_000_000, message="Quantidade inválida.")])
    unit = StringField("Unidade", filters=[_strip], default="un", validators=[DataRequired(message="Informe a unidade."), Length(max=20)])
    min_quantity = IntegerField("Estoque mínimo", default=0, validators=[Optional(), NumberRange(min=0, max=1_000_000, message="Valor inválido.")])
    cost_cents = MoneyField("Custo unitário (R$)")
    supplier = StringField("Fornecedor", filters=[_strip], validators=[Optional(), Length(max=120)])
    expires_on = DateField("Validade", format="%Y-%m-%d", validators=[Optional()])
    notes = TextAreaField("Observações", filters=[_strip], validators=[Optional(), Length(max=3000)])

    def __init__(self, *args, editing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing = editing
        cats = Category.query.filter_by(kind=CategoryKind.INVENTORY, is_active=True).order_by(Category.name).all()
        self.category_id.choices = [(0, "Sem categoria")] + [(c.id, c.name) for c in cats]

    def validate_cost_cents(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("O custo não pode ser negativo.")

    def validate_expires_on(self, field):
        if field.data and field.data.year > 2100:
            raise ValidationError("Data inválida.")

    def cleaned(self) -> dict:
        d = self.data
        return {"name": d["name"], "category_id": d.get("category_id") or None, "unit": d["unit"],
                "min_quantity": d.get("min_quantity") or 0, "cost_cents": d.get("cost_cents") or 0,
                "supplier": d.get("supplier") or None, "expires_on": d.get("expires_on"), "notes": d.get("notes") or None}


class MovementForm(FlaskForm):
    type = SelectField("Tipo", choices=MovementType.choices(), validate_choice=True)
    quantity = IntegerField("Quantidade", validators=[InputRequired(message="Informe a quantidade."),
                                                     NumberRange(min=0, max=1_000_000, message="Quantidade inválida.")])
    reason = StringField("Motivo", filters=[_strip], validators=[Optional(), Length(max=200)])
