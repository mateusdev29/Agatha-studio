"""Filtro de período compartilhado (Financeiro, Dashboard, Satisfação). Datas inclusivas."""
from dataclasses import dataclass
from datetime import date, timedelta

from app.utils.dates import today_local

PRESETS = [("mes", "Este mês"), ("mes_anterior", "Mês anterior"), ("30d", "Últimos 30 dias"),
           ("ano", "Este ano"), ("tudo", "Todo o período")]
MAX_CUSTOM_DAYS = 3660


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    key: str            # chave do preset ou "custom"

    @property
    def label(self) -> str:
        if self.key == "custom":
            return f"{self.start:%d/%m/%Y} a {self.end:%d/%m/%Y}"
        return dict(PRESETS)[self.key]

    @property
    def args(self) -> dict:
        """Parâmetros de URL que reproduzem este período (para links e paginação)."""
        return {"de": self.start.isoformat(), "ate": self.end.isoformat()} if self.key == "custom" else {"periodo": self.key}


def _iso(value):
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return None


def parse_period(args, default: str = "mes") -> Period:
    today = today_local()
    start, end = _iso(args.get("de")), _iso(args.get("ate"))
    if start and end and start <= end and (end - start).days <= MAX_CUSTOM_DAYS and start.year >= 2000 and end.year <= 2100:
        return Period(start, end, "custom")
    key = args.get("periodo")
    key = key if key in dict(PRESETS) else default
    first = today.replace(day=1)
    if key == "mes":
        return Period(first, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1), key)
    if key == "mes_anterior":
        last = first - timedelta(days=1)
        return Period(last.replace(day=1), last, key)
    if key == "30d":
        return Period(today - timedelta(days=29), today, key)
    if key == "ano":
        return Period(date(today.year, 1, 1), date(today.year, 12, 31), key)
    return Period(date(2000, 1, 1), date(2100, 12, 31), "tudo")
