import pytest

from app.utils.money import format_input, parse_brl


@pytest.mark.parametrize("text,cents", [
    ("0", 0), ("1200", 120000), ("1.200", 120000), ("1.200,50", 120050), ("1200,5", 120050),
    ("1200,50", 120050), ("R$ 1.200,50", 120050), (" 12 ", 1200), ("1200.50", 120050), ("12.5", 1250),
    ("0,99", 99), ("10.000,00", 1000000),
])
def test_parse_brl_valid(text, cents):
    assert parse_brl(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "-5", "1,2,3", "1.2.3", "12,345", "1,234.56", "R$", "1e5", "٣٤", "١٢٣,٤٥", "1000000,01", "1.234.567"])
def test_parse_brl_invalid(text):
    with pytest.raises(ValueError):
        parse_brl(text)


def test_limit_is_one_million():
    assert parse_brl("1.000.000,00") == 100_000_000


def test_format_input_roundtrip():
    assert format_input(120050) == "1200,50" and format_input(5) == "0,05" and format_input(None) == ""
    for cents in (0, 1, 99, 100, 120050, 99999999):
        assert parse_brl(format_input(cents)) == cents
