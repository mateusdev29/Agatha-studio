"""Números da Visão Geral. Tudo vem do banco; nenhum valor fixo."""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import ActivityLog, Appointment, FinancialTransaction, Project, Quote
from app.models.enums import (AppointmentStatus, ProjectStatus, QuoteStatus,
                              TransactionStatus, TransactionType)
from app.utils.dates import now_local, today_local

ACTIVE_APPOINTMENT = [AppointmentStatus.WAITING, AppointmentStatus.CONFIRMED, AppointmentStatus.DONE]
UPCOMING = [AppointmentStatus.WAITING, AppointmentStatus.CONFIRMED]


@dataclass
class Overview:
    greeting: str
    today: object
    appointments_today: int
    next_today: datetime | None
    revenue_month_cents: int
    expenses_month_cents: int
    projects_in_progress: int
    pending_quotes: int
    upcoming: list = field(default_factory=list)
    activities: list = field(default_factory=list)

    @property
    def profit_month_cents(self) -> int:
        return self.revenue_month_cents - self.expenses_month_cents


def _greeting(hour: int) -> str:
    return "Bom dia" if hour < 12 else "Boa tarde" if hour < 18 else "Boa noite"


def _month_sum(kind, month_start, next_month) -> int:
    return db.session.query(func.coalesce(func.sum(FinancialTransaction.amount_cents), 0)).filter(
        FinancialTransaction.type == kind,
        FinancialTransaction.status == TransactionStatus.PAID,
        FinancialTransaction.date >= month_start,
        FinancialTransaction.date < next_month,
    ).scalar()


def get_overview() -> Overview:
    now = now_local()
    today = today_local()
    day_start = datetime.combine(today, time.min)
    day_end = day_start + timedelta(days=1)
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)

    todays = (Appointment.query
              .filter(Appointment.starts_at >= day_start, Appointment.starts_at < day_end,
                      Appointment.status.in_(ACTIVE_APPOINTMENT)))
    next_today = (todays.filter(Appointment.starts_at >= now, Appointment.status.in_(UPCOMING))
                  .order_by(Appointment.starts_at).first())

    return Overview(
        greeting=_greeting(now.hour),
        today=today,
        appointments_today=todays.count(),
        next_today=next_today.starts_at if next_today else None,
        revenue_month_cents=_month_sum(TransactionType.INCOME, month_start, next_month),
        expenses_month_cents=_month_sum(TransactionType.EXPENSE, month_start, next_month),
        projects_in_progress=Project.query.filter(Project.status == ProjectStatus.IN_PROGRESS).count(),
        pending_quotes=Quote.query.filter(Quote.status.in_([QuoteStatus.SENT, QuoteStatus.WAITING])).count(),
        upcoming=(Appointment.query.options(joinedload(Appointment.client))
                  .filter(Appointment.starts_at >= now, Appointment.status.in_(UPCOMING))
                  .order_by(Appointment.starts_at).limit(5).all()),
        activities=ActivityLog.query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(8).all(),
    )
