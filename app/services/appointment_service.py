"""Regras da Agenda: conflitos, máquina de estados e remarcação (sem request/response)."""
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Appointment, Client, Project
from app.models.enums import AppointmentStatus
from app.services.activity_service import log_activity
from app.services.deposit_service import deposit_transaction, move_deposit
from app.utils.dates import now_local

S = AppointmentStatus
MAX_DURATION = timedelta(minutes=720)

TRANSITIONS = {
    S.WAITING: {S.CONFIRMED, S.DONE, S.CANCELED},
    S.CONFIRMED: {S.DONE, S.CANCELED},
    S.CANCELED: {S.WAITING},
    S.DONE: set(),
    S.RESCHEDULED: set(),
}
EDITABLE = {S.WAITING, S.CONFIRMED}
BLOCKING = [S.WAITING, S.CONFIRMED, S.DONE]       # ocupam o horário (cancelado/remarcado liberam)


class AppointmentError(Exception):
    """Regra violada; a mensagem é segura para mostrar à usuária."""


def is_editable(appt: Appointment) -> bool:
    return appt.status in EDITABLE


def find_conflict(starts_at: datetime, duration_minutes: int, exclude_id: int | None = None) -> Appointment | None:
    """Atendimento ativo que se sobrepõe ao intervalo (há uma única profissional)."""
    end = starts_at + timedelta(minutes=duration_minutes)
    candidates = (Appointment.query.options(joinedload(Appointment.client))
                  .filter(Appointment.status.in_(BLOCKING),
                          Appointment.starts_at < end,
                          Appointment.starts_at > starts_at - MAX_DURATION)
                  .order_by(Appointment.starts_at).all())
    for other in candidates:
        if other.id != exclude_id and other.starts_at < end and other.ends_at > starts_at:
            return other
    return None


def _ensure_free(starts_at, duration, exclude_id=None):
    other = find_conflict(starts_at, duration, exclude_id)
    if other:
        raise AppointmentError(
            f"Conflito de horário com {other.client.name} ({other.starts_at:%H:%M}–{other.ends_at:%H:%M}).")


def _ensure_consistent(data: dict) -> None:
    client = db.session.get(Client, data["client_id"])
    if client is None or client.archived_at is not None:
        raise AppointmentError("Escolha um cliente ativo.")
    if data.get("project_id"):
        project = db.session.get(Project, data["project_id"])
        if project is None or project.client_id != data["client_id"]:
            raise AppointmentError("O projeto escolhido não pertence a este cliente.")


def create_appointment(data: dict, user) -> Appointment:
    _ensure_consistent(data)
    _ensure_free(data["starts_at"], data["duration_minutes"])
    appt = Appointment(**data, status=S.WAITING)
    db.session.add(appt)
    db.session.flush()
    log_activity("created", f"Atendimento agendado: {appt.client.name}, {appt.starts_at:%d/%m %H:%M}",
                 user, "appointment", appt.id)
    db.session.commit()
    return appt


def update_appointment(appt: Appointment, data: dict, user) -> Appointment:
    if not is_editable(appt):
        raise AppointmentError("Só atendimentos aguardando ou confirmados podem ser editados.")
    if deposit_transaction(appt):                 # sinal já lançado: o valor passa a ser alterado só no Financeiro
        data = {k: v for k, v in data.items() if k != "deposit_cents"}
    _ensure_consistent({**data, "client_id": data["client_id"]})
    _ensure_free(data["starts_at"], data["duration_minutes"], exclude_id=appt.id)
    for key, value in data.items():
        setattr(appt, key, value)
    log_activity("updated", f"Atendimento atualizado: {appt.client.name}, {appt.starts_at:%d/%m %H:%M}",
                 user, "appointment", appt.id)
    db.session.commit()
    return appt


def change_status(appt: Appointment, target: AppointmentStatus, user) -> Appointment:
    if target not in TRANSITIONS[appt.status]:
        raise AppointmentError(f"Não é possível mudar de “{appt.status.label}” para “{target.label}”.")
    if target == S.DONE and appt.starts_at > now_local():
        raise AppointmentError("Só é possível marcar como realizado depois do início do atendimento.")
    if appt.status == S.CANCELED:                                  # reativar precisa do horário livre
        _ensure_free(appt.starts_at, appt.duration_minutes, exclude_id=appt.id)
    appt.status = target
    log_activity("status", f"Atendimento de {appt.client.name} ({appt.starts_at:%d/%m %H:%M}): {target.label.lower()}",
                 user, "appointment", appt.id)
    db.session.commit()
    return appt


def reschedule(appt: Appointment, new_start: datetime, duration_minutes: int, user) -> Appointment:
    """Marca o original como 'remarcado' (histórico) e cria o novo, aguardando confirmação."""
    if not is_editable(appt):
        raise AppointmentError("Só atendimentos aguardando ou confirmados podem ser remarcados.")
    if new_start == appt.starts_at:
        raise AppointmentError("Escolha uma data ou horário diferente do atual.")
    _ensure_free(new_start, duration_minutes, exclude_id=appt.id)

    old_label = f"{appt.starts_at:%d/%m/%Y %H:%M}"
    new = Appointment(client_id=appt.client_id, project_id=appt.project_id, session_id=appt.session_id,
                      starts_at=new_start, duration_minutes=duration_minutes, service=appt.service,
                      price_cents=appt.price_cents, deposit_cents=appt.deposit_cents, status=S.WAITING,
                      notes="\n".join(x for x in [appt.notes, f"Remarcado de {old_label}."] if x))
    try:
        appt.status = S.RESCHEDULED
        appt.deposit_cents = 0            # o sinal acompanha o novo horário (não conta duas vezes)
        db.session.add(new)
        db.session.flush()
        move_deposit(appt, new)                    # o lançamento do sinal (se houver) acompanha o novo horário
        log_activity("status", f"Atendimento de {appt.client.name} remarcado: {old_label} → {new_start:%d/%m/%Y %H:%M}",
                     user, "appointment", new.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return new
