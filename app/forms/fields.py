from wtforms import SelectField as WTSelectField, StringField
from wtforms.fields import SelectChoice

from app.utils.money import format_input, parse_brl


def _select_choices(choices):
    """Convert legacy project tuples into WTForms' explicit choice objects."""
    if choices is None:
        return None
    if callable(choices):
        return lambda: _select_choices(choices())
    normalized = []
    for choice in choices:
        if isinstance(choice, SelectChoice):
            normalized.append(choice)
        elif isinstance(choice, str):
            normalized.append(SelectChoice(choice))
        elif isinstance(choice, tuple) and len(choice) in (2, 3):
            value, label, *render_kw = choice
            normalized.append(SelectChoice(value, label, render_kw[0] if render_kw else {}))
        else:
            raise TypeError(f"Unsupported select choice: {choice!r}")
    return normalized


class SelectField(WTSelectField):
    """SelectField that stores only WTForms SelectChoice values."""

    def __init__(self, *args, choices=None, **kwargs):
        super().__init__(*args, choices=_select_choices(choices), **kwargs)

    @property
    def choices(self):
        return WTSelectField.choices.fget(self)

    @choices.setter
    def choices(self, value):
        WTSelectField.choices.fset(self, _select_choices(value))


class MoneyField(StringField):
    """Campo de dinheiro: o usuário digita '1.200,50'; `data` é um inteiro em centavos.
    Vazio vira None (o formulário decide se isso significa 0 ou erro)."""

    def process_formdata(self, valuelist):
        self.data = None
        raw = (valuelist[0] if valuelist else "").strip()
        if not raw:
            return
        try:
            self.data = parse_brl(raw)
        except ValueError:
            raise ValueError("Valor inválido. Use o formato 1.200,50.")

    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        return format_input(self.data)
