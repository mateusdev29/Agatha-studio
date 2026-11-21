"""Datas no fuso do estúdio. Agenda usa horário local sem fuso; created_at é UTC."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app


def studio_tz() -> ZoneInfo:
    return ZoneInfo(current_app.config["STUDIO_TIMEZONE"])


def now_local() -> datetime:
    """Agora, no horário local do estúdio (sem tzinfo, comparável com starts_at)."""
    return datetime.now(studio_tz()).replace(tzinfo=None)


def today_local() -> date:
    return now_local().date()


def utc_to_local(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone(studio_tz()).replace(tzinfo=None)
