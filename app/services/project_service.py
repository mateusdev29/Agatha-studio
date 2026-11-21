"""Regras do módulo Projetos e de suas sessões (sem request/response)."""
from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Appointment, Client, FinancialTransaction, Project, ProjectSession
from app.models.enums import ProjectStatus, SessionStatus, TransactionStatus, TransactionType
from app.services.activity_service import log_activity

PER_PAGE = 15


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_projects(q: str = "", status: str = "", page: int = 1, client_id: int | None = None):
    stmt = db.select(Project).join(Client).options(joinedload(Project.client), joinedload(Project.body_region))
    if status in {s.value for s in ProjectStatus}:
        stmt = stmt.where(Project.status == ProjectStatus(status))
    if client_id:
        stmt = stmt.where(Project.client_id == client_id)
    q = (q or "").strip()
    if q:
        pattern = _like(q)
        stmt = stmt.where(or_(Project.name.ilike(pattern, escape="\\"),
                              Client.name.ilike(pattern, escape="\\"),
                              Project.style.ilike(pattern, escape="\\")))
    return db.paginate(stmt.order_by(Project.updated_at.desc(), Project.id.desc()),
                       page=page, per_page=PER_PAGE, error_out=False)


def create_project(data: dict, user) -> Project:
    project = Project(**data)
    db.session.add(project)
    db.session.flush()
    log_activity("created", f"Projeto criado: {project.name}", user, "project", project.id)
    db.session.commit()
    return project


def update_project(project: Project, data: dict, user) -> Project:
    for key, value in data.items():
        setattr(project, key, value)
    log_activity("updated", f"Projeto atualizado: {project.name}", user, "project", project.id)
    db.session.commit()
    return project


@dataclass
class ProjectFinancials:
    paid_cents: int
    pending_cents: int
    sessions_total_cents: int
    sessions_count: int


def project_financials(project: Project) -> ProjectFinancials:
    def income(status):
        return db.session.query(func.coalesce(func.sum(FinancialTransaction.amount_cents), 0)).filter(
            FinancialTransaction.project_id == project.id,
            FinancialTransaction.type == TransactionType.INCOME,
            FinancialTransaction.status == status).scalar()

    active = [s for s in project.sessions if s.status != SessionStatus.CANCELED]
    return ProjectFinancials(
        paid_cents=income(TransactionStatus.PAID),
        pending_cents=income(TransactionStatus.PENDING),
        sessions_total_cents=sum(s.price_cents for s in active),
        sessions_count=len(active),
    )


# ---------- Sessões ----------
def add_session(project: Project, data: dict, user) -> ProjectSession:
    session = ProjectSession(project_id=project.id, **data)
    db.session.add(session)
    db.session.flush()
    log_activity("created", f"Sessão adicionada ao projeto {project.name}", user, "project", project.id)
    db.session.commit()
    return session


def update_session(session: ProjectSession, data: dict, user) -> ProjectSession:
    for key, value in data.items():
        setattr(session, key, value)
    log_activity("updated", f"Sessão atualizada no projeto {session.project.name}", user, "project", session.project_id)
    db.session.commit()
    return session


class SessionInUse(Exception):
    """A sessão está vinculada a atendimentos da agenda."""


def delete_session(session: ProjectSession, user) -> None:
    if Appointment.query.filter_by(session_id=session.id).first():
        raise SessionInUse()
    log_activity("deleted", f"Sessão removida do projeto {session.project.name}", user, "project", session.project_id)
    db.session.delete(session)
    db.session.commit()
