from wtforms import StringField

from app.utils.money import format_input, parse_brl


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
