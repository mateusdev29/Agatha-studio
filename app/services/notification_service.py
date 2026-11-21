"""Avisos do sino, calculados a partir do banco (nada é fixo no código)."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy.orm import joinedload

from app.models import Appointment, InventoryItem, Quote
from app.models.enums import AppointmentStatus, QuoteStatus
from app.utils.dates import now_local, today_local

MAX_NOTIFICATIONS = 10
QUOTE_WARNING_DAYS = 3
EXPIRY_WARNING_DAYS = 30


@dataclass(frozen=True)
class Notification:
    title: str
    detail: str
    tone: str      # warning | danger | info
    icon: str
    path: str


def get_notifications() -> list[Notification]:
    now, today = now_local(), today_local()
    items: list[Notification] = []

    # 1) Atendimentos aguardando confirmação nas próximas 48 h
    waiting = (Appointment.query.options(joinedload(Appointment.client))
               .filter(Appointment.status == AppointmentStatus.WAITING,
                       Appointment.starts_at >= now,
                       Appointment.starts_at <= now + timedelta(hours=48))
               .order_by(Appointment.starts_at).limit(MAX_NOTIFICATIONS).all())
    for a in waiting:
        items.append(Notification(
            f"Confirmar atendimento de {a.client.name}",
            f"{a.starts_at:%d/%m} às {a.starts_at:%H:%M}", "warning", "clock", "/agenda"))

    # 2) Orçamentos abertos que vencem em breve e os que expiraram na última semana
    quotes = (Quote.query.options(joinedload(Quote.client))
              .filter(Quote.status.in_([QuoteStatus.SENT, QuoteStatus.WAITING]),
                      Quote.valid_until.isnot(None), Quote.valid_until >= today,
                      Quote.valid_until <= today + timedelta(days=QUOTE_WARNING_DAYS))
              .order_by(Quote.valid_until).limit(MAX_NOTIFICATIONS).all())
    for q in quotes:
        items.append(Notification(f"Orçamento de {q.client.name} vence em breve",
                                  f"Validade: {q.valid_until:%d/%m/%Y}", "warning", "file", "/orcamentos"))
    expired = (Quote.query.options(joinedload(Quote.client))
               .filter(Quote.status == QuoteStatus.EXPIRED, Quote.valid_until >= today - timedelta(days=7))
               .order_by(Quote.valid_until.desc()).limit(MAX_NOTIFICATIONS).all())
    for q in expired:
        items.append(Notification(f"Orçamento de {q.client.name} expirou",
                                  f"Validade: {q.valid_until:%d/%m/%Y}", "danger", "file", "/orcamentos"))

    # 3) Estoque baixo
    low = (InventoryItem.query
           .filter(InventoryItem.is_active.is_(True), InventoryItem.quantity <= InventoryItem.min_quantity)
           .order_by(InventoryItem.quantity).limit(MAX_NOTIFICATIONS).all())
    for i in low:
        items.append(Notification(
            f"Estoque baixo: {i.name}", f"{i.quantity} {i.unit} (mínimo {i.min_quantity})",
            "warning", "box", "/estoque"))

    # 4) Produtos perto da validade
    expiring = (InventoryItem.query
                .filter(InventoryItem.is_active.is_(True), InventoryItem.expires_on.isnot(None),
                        InventoryItem.expires_on <= today + timedelta(days=EXPIRY_WARNING_DAYS))
                .order_by(InventoryItem.expires_on).limit(MAX_NOTIFICATIONS).all())
    for i in expiring:
        expired = i.expires_on < today
        items.append(Notification(
            f"{i.name} " + ("vencido" if expired else "vence em breve"),
            f"Validade: {i.expires_on:%d/%m/%Y}", "danger" if expired else "info", "alert", "/estoque"))

    return items[:MAX_NOTIFICATIONS]
