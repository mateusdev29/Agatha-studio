"""Filtros Jinja em pt-BR."""
from datetime import date, datetime, timedelta

from app.utils.dates import now_local, today_local, utc_to_local

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
WEEKDAYS_SHORT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]


def format_brl(cents: int | None) -> str:
    """1234567 -> 'R$ 12.345,67' (valores em centavos)."""
    cents = int(cents or 0)
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def format_date_long(value: date) -> str:
    """'terça-feira, 29 de setembro'"""
    return f"{WEEKDAYS[value.weekday()]}, {value.day} de {MONTHS[value.month - 1]}"


def month_year(value: date) -> str:
    return f"{MONTHS[value.month - 1]} de {value.year}"


def day_label(value: datetime) -> str:
    """'Hoje', 'Amanhã' ou 'qua, 30/09'."""
    today = today_local()
    if value.date() == today:
        return "Hoje"
    if value.date() == today + timedelta(days=1):
        return "Amanhã"
    return f"{WEEKDAYS_SHORT[value.weekday()]}, {value:%d/%m}"


def format_relative(utc_value: datetime) -> str:
    """Tempo relativo para registros em UTC: 'agora', 'há 5 min', 'ontem às 14:32'."""
    local = utc_to_local(utc_value)
    delta = now_local() - local
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "agora"
    if seconds < 3600:
        return f"há {seconds // 60} min"
    if local.date() == today_local():
        return f"há {seconds // 3600} h"
    if local.date() == today_local() - timedelta(days=1):
        return f"ontem às {local:%H:%M}"
    return f"{local:%d/%m} às {local:%H:%M}"


STATUS_TONES = {
    # atendimentos
    "aguardando": "warning", "confirmado": "success", "realizado": "neutral",
    "cancelado": "danger", "remarcado": "accent",
    # projetos
    "orcamento": "warning", "aprovado": "success", "em_andamento": "accent", "concluido": "neutral",
    # sessões
    "agendada": "accent", "realizada": "neutral", "cancelada": "danger",
    # orçamentos
    "rascunho": "neutral", "enviado": "accent", "aguardando_resposta": "warning",
    "recusado": "danger", "expirado": "danger",
    # financeiro
    "pendente": "warning", "pago": "success",
}


def status_tone(status) -> str:
    """Cor do selo para qualquer enum de status (aceita o enum ou seu valor)."""
    return STATUS_TONES.get(getattr(status, "value", status), "neutral")


def age_from(birth: date | None) -> int | None:
    if not birth:
        return None
    today = today_local()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def date_br(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def local_date(utc_value: datetime | None) -> str:
    """Data (dd/mm/aaaa) de um registro gravado em UTC, no fuso do estúdio."""
    return date_br(utc_to_local(utc_value)) if utc_value else ""


def register_filters(app):
    app.jinja_env.filters.update(
        brl=format_brl,
        date_long=format_date_long,
        month_year=month_year,
        day_label=day_label,
        relative=format_relative,
        tone=status_tone,
        date_br=date_br,
        local_date=local_date,
        age=age_from,
    )
