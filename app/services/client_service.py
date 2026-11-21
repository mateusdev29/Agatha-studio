"""Regras do módulo Clientes (sem request/response)."""
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import func, or_

from app.extensions import db
from sqlalchemy.orm import joinedload

from app.models import Appointment, Client, Evaluation, FinancialTransaction, Project, Quote, AnamnesisResponse
from app.models.base import utcnow
from app.models.enums import AppointmentStatus, TransactionStatus, TransactionType
from app.services.activity_service import log_activity
from app.utils.dates import now_local, utc_to_local

PER_PAGE = 15
STATUS_FILTERS = {"ativos", "arquivados", "todos"}


def _like(term: str) -> str:
    """Escapa curingas (%, _) para a busca tratar o texto digitado literalmente."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_clients(q: str = "", status: str = "ativos", page: int = 1):
    stmt = db.select(Client)
    if status == "arquivados":
        stmt = stmt.where(Client.archived_at.is_not(None))
    elif status != "todos":
        stmt = stmt.where(Client.archived_at.is_(None))

    q = (q or "").strip()
    if q:
        pattern = _like(q.lstrip("@"))
        stmt = stmt.where(or_(
            Client.name.ilike(pattern, escape="\\"),
            Client.phone.ilike(pattern, escape="\\"),
            Client.email.ilike(pattern, escape="\\"),
            Client.instagram.ilike(pattern, escape="\\"),
        ))
    return db.paginate(stmt.order_by(func.lower(Client.name), Client.id),
                       page=page, per_page=PER_PAGE, error_out=False)


def create_client(data: dict, user) -> Client:
    client = Client(**data)
    db.session.add(client)
    db.session.flush()
    log_activity("created", f"Cliente cadastrado: {client.name}", user, "client", client.id)
    db.session.commit()
    return client


def update_client(client: Client, data: dict, user) -> Client:
    for key, value in data.items():
        setattr(client, key, value)
    log_activity("updated", f"Cliente atualizado: {client.name}", user, "client", client.id)
    db.session.commit()
    return client


def archive_client(client: Client, user) -> None:
    client.archived_at = utcnow()
    log_activity("archived", f"Cliente arquivado: {client.name}", user, "client", client.id)
    db.session.commit()


def restore_client(client: Client, user) -> None:
    client.archived_at = None
    log_activity("restored", f"Cliente restaurado: {client.name}", user, "client", client.id)
    db.session.commit()


# ---------- Página individual ----------
@dataclass
class ClientSummary:
    projects: int
    appointments_done: int
    paid_cents: int
    pending_cents: int
    average_score: float | None
    evaluations: int
    next_appointment: object | None
    last_appointment: object | None


def client_summary(client: Client) -> ClientSummary:
    now = now_local()

    def income(status):
        return db.session.query(func.coalesce(func.sum(FinancialTransaction.amount_cents), 0)).filter(
            FinancialTransaction.client_id == client.id,
            FinancialTransaction.type == TransactionType.INCOME,
            FinancialTransaction.status == status).scalar()

    done = client.appointments.filter_by(status=AppointmentStatus.DONE)
    avg = db.session.query(func.avg(Evaluation.score)).filter(Evaluation.client_id == client.id).scalar()
    return ClientSummary(
        projects=client.projects.count(),
        appointments_done=done.count(),
        paid_cents=income(TransactionStatus.PAID),
        pending_cents=income(TransactionStatus.PENDING),
        average_score=round(float(avg), 1) if avg is not None else None,
        evaluations=client.evaluations.count(),
        next_appointment=(client.appointments
                          .filter(Appointment.starts_at >= now,
                                  Appointment.status.in_([AppointmentStatus.WAITING, AppointmentStatus.CONFIRMED]))
                          .order_by(Appointment.starts_at).first()),
        last_appointment=done.order_by(Appointment.starts_at.desc()).first(),
    )


@dataclass
class HistoryEvent:
    when: datetime
    kind: str       # appointment | quote | project | payment | evaluation | anamnesis
    title: str
    detail: str = ""


def _dt(value) -> datetime:
    return datetime.combine(value, time.min) if isinstance(value, date) and not isinstance(value, datetime) else value


def client_history(client: Client, limit: int = 200) -> list[HistoryEvent]:
    """Linha do tempo completa, da mais recente para a mais antiga."""
    from app.utils.formatting import format_brl

    events: list[HistoryEvent] = []
    for a in client.appointments:
        events.append(HistoryEvent(a.starts_at, "appointment",
                                   f"Atendimento {a.status.label.lower()}", a.service or ""))
    for q in client.quotes:
        events.append(HistoryEvent(utc_to_local(q.created_at), "quote",
                                   f"Orçamento {q.status.label.lower()}", format_brl(q.price_cents)))
    for p in client.projects:
        events.append(HistoryEvent(utc_to_local(p.created_at), "project", f"Projeto: {p.name}", p.status.label))
    for t in client.transactions.filter_by(type=TransactionType.INCOME):
        events.append(HistoryEvent(_dt(t.date), "payment",
                                   f"Pagamento {t.status.label.lower()}: {format_brl(t.amount_cents)}", t.description))
    for e in client.evaluations:
        events.append(HistoryEvent(_dt(e.evaluated_on), "evaluation", f"Avaliação: {e.score}/10", e.comment or ""))
    for r in client.anamnesis_responses:
        events.append(HistoryEvent(utc_to_local(r.created_at), "anamnesis",
                                   "Ficha de anamnese registrada", "Aceite registrado" if r.accepted else ""))
    events.sort(key=lambda ev: ev.when, reverse=True)
    return events[:limit]


def tab_items(client: Client, tab: str) -> list:
    """Registros exibidos em cada aba da página do cliente (mais recentes primeiro)."""
    if tab == "projetos":
        return (client.projects.options(joinedload(Project.body_region))
                .order_by(Project.created_at.desc()).all())
    if tab == "agenda":
        return client.appointments.order_by(Appointment.starts_at.desc()).all()
    if tab == "orcamentos":
        return client.quotes.order_by(Quote.created_at.desc()).all()
    if tab == "pagamentos":
        return (client.transactions.filter_by(type=TransactionType.INCOME)
                .order_by(FinancialTransaction.date.desc(), FinancialTransaction.id.desc()).all())
    if tab == "anamnese":
        return client.anamnesis_responses.order_by(AnamnesisResponse.created_at.desc()).all()
    if tab == "avaliacoes":
        return client.evaluations.order_by(Evaluation.evaluated_on.desc()).all()
    return []
