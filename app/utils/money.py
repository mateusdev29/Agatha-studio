"""Valores monetários: o sistema guarda centavos inteiros; o usuário digita no padrão brasileiro."""
import re

MAX_CENTS = 100_000_000  # R$ 1.000.000,00

_THOUSANDS_ONLY = re.compile(r"^\d{1,3}(\.\d{3})+$", re.ASCII)
_DOT_DECIMAL = re.compile(r"^\d+\.\d{1,2}$", re.ASCII)
_BR = re.compile(r"^\d{1,3}(\.\d{3})*,\d{1,2}$|^\d+,\d{1,2}$", re.ASCII)  # ASCII: \d casaria dígitos de outros alfabetos
_DIGITS = re.compile(r"^\d+$", re.ASCII)


def parse_brl(text: str) -> int:
    """'1.200,50' | 'R$ 1200' | '1200.5' -> centavos. Levanta ValueError se inválido.

    Regra: com vírgula, o ponto é separador de milhar ("1.200,50"). Sem vírgula,
    "1.200" é milhar e "12.5" é decimal.
    """
    raw = re.sub(r"\s|R\$", "", text or "")
    if not raw:
        raise ValueError("vazio")
    if _BR.match(raw):
        reais, _, cents = raw.replace(".", "").partition(",")
    elif _THOUSANDS_ONLY.match(raw):
        reais, cents = raw.replace(".", ""), "0"
    elif _DOT_DECIMAL.match(raw):
        reais, _, cents = raw.partition(".")
    elif _DIGITS.match(raw):
        reais, cents = raw, "0"
    else:
        raise ValueError("formato inválido")
    value = int(reais) * 100 + int(cents.ljust(2, "0"))
    if value > MAX_CENTS:
        raise ValueError("valor muito alto")
    return value


def format_input(cents: int | None) -> str:
    """Valor para preencher o campo do formulário: 120050 -> '1200,50'."""
    if cents is None:
        return ""
    return f"{cents // 100},{cents % 100:02d}"
