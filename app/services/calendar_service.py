"""Monta as visões da agenda (dia, semana, mês). Semana começa na segunda-feira."""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import joinedload

from app.models import Appointment
from app.utils.dates import today_local
from app.utils.formatting import MONTHS, WEEKDAYS, WEEKDAYS_SHORT

VIEWS = ("dia", "semana", "mes")
MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


@dataclass
class Day:
    date: date
    items: list = field(default_factory=list)
    in_range: bool = True

    @property
    def is_today(self) -> bool:
        return self.date == today_local()


@dataclass
class Calendar:
    view: str
    anchor: date
    title: str
    days: list
    prev: date
    next: date


def parse_view(value) -> str:
    return value if value in VIEWS else "semana"


def parse_date(value) -> date:
    try:
        parsed = date.fromisoformat(value or "")
    except ValueError:
        return today_local()
    return parsed if 2000 <= parsed.year <= 2100 else today_local()


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _shift_month(d: date, step: int) -> date:
    month = d.month - 1 + step
    return date(d.year + month // 12, month % 12 + 1, 1)


def _title(view: str, anchor: date, first: date, last: date) -> str:
    if view == "dia":
        return f"{WEEKDAYS[anchor.weekday()]}, {anchor.day} de {MONTHS[anchor.month - 1]} de {anchor.year}"
    if view == "semana":
        return (f"{first.day} {MONTHS_SHORT[first.month - 1]} – {last.day} {MONTHS_SHORT[last.month - 1]} {last.year}")
    return f"{MONTHS[anchor.month - 1]} de {anchor.year}"


def build_calendar(view: str, anchor: date) -> Calendar:
    if view == "dia":
        first, last = anchor, anchor
        prev, nxt = anchor - timedelta(days=1), anchor + timedelta(days=1)
    elif view == "semana":
        first = _monday(anchor)
        last = first + timedelta(days=6)
        prev, nxt = anchor - timedelta(days=7), anchor + timedelta(days=7)
    else:
        month_first = anchor.replace(day=1)
        month_last = _shift_month(month_first, 1) - timedelta(days=1)
        first, last = _monday(month_first), month_last + timedelta(days=6 - month_last.weekday())
        prev, nxt = _shift_month(month_first, -1), _shift_month(month_first, 1)

    days = [Day(first + timedelta(days=i)) for i in range((last - first).days + 1)]
    if view == "mes":
        for d in days:
            d.in_range = d.date.month == anchor.month

    start = datetime.combine(first, time.min)
    end = datetime.combine(last + timedelta(days=1), time.min)
    appts = (Appointment.query.options(joinedload(Appointment.client), joinedload(Appointment.project))
             .filter(Appointment.starts_at >= start, Appointment.starts_at < end)
             .order_by(Appointment.starts_at).all())
    by_day = {d.date: d for d in days}
    for a in appts:
        by_day[a.starts_at.date()].items.append(a)
    return Calendar(view, anchor, _title(view, anchor, first, last), days, prev, nxt)


WEEKDAY_HEADERS = WEEKDAYS_SHORT
