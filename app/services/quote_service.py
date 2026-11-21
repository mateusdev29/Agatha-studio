"""Regras do módulo Orçamentos: máquina de estados, aprovação, projeto gerado e expiração."""
from datetime import timedelta

from flask import current_app
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Client, Project, Quote
from app.models.enums import ProjectStatus, QuoteStatus
from app.services.activity_service import log_activity
from app.services.settings_service import studio_name
from app.utils.dates import now_local, today_local
from app.utils.formatting import format_brl

PER_PAGE = 15
S = QuoteStatus

# Quem pode ir para onde. Aprovação tem fluxo próprio (approve), por causa do projeto.
TRANSITIONS = {
    S.DRAFT: {S.SENT},
    S.SENT: {S.WAITING, S.APPROVED, S.REJECTED},
    S.WAITING: {S.APPROVED, S.REJECTED},
    S.REJECTED: {S.DRAFT},
    S.EXPIRED: {S.DRAFT},
    S.APPROVED: set(),
}
OPEN_STATUSES = [S.SENT, S.WAITING]


class QuoteError(Exception):
    """Regra de negócio violada; a mensagem é segura para mostrar à usuária."""


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_quotes(q: str = "", status: str = "", page: int = 1, client_id: int | None = None):
    stmt = db.select(Quote).join(Client).options(joinedload(Quote.client))
    if status in {s.value for s in QuoteStatus}:
        stmt = stmt.where(Quote.status == QuoteStatus(status))
    if client_id:
        stmt = stmt.where(Quote.client_id == client_id)
    q = (q or "").strip()
    if q:
        pattern = _like(q)
        stmt = stmt.where(or_(Quote.description.ilike(pattern, escape="\\"),
                              Client.name.ilike(pattern, escape="\\"),
                              Quote.style.ilike(pattern, escape="\\")))
    return db.paginate(stmt.order_by(Quote.created_at.desc(), Quote.id.desc()),
                       page=page, per_page=PER_PAGE, error_out=False)


def is_locked(quote: Quote) -> bool:
    """Com projeto gerado, o orçamento vira registro histórico (não diverge do projeto)."""
    return quote.project_id is not None


def create_quote(data: dict, user) -> Quote:
    quote = Quote(**data, status=S.DRAFT)
    db.session.add(quote)
    db.session.flush()
    log_activity("created", f"Orçamento criado para {quote.client.name}", user, "quote", quote.id)
    db.session.commit()
    return quote


def update_quote(quote: Quote, data: dict, user) -> Quote:
    if is_locked(quote):
        raise QuoteError("Este orçamento já gerou um projeto e não pode mais ser editado.")
    for key, value in data.items():
        setattr(quote, key, value)
    log_activity("updated", f"Orçamento atualizado: {quote.client.name}", user, "quote", quote.id)
    db.session.commit()
    return quote


def _ensure_can_leave_draft(quote: Quote) -> None:
    if not quote.price_cents or quote.price_cents <= 0:
        raise QuoteError("Defina o valor do orçamento antes de enviá-lo.")
    if quote.valid_until and quote.valid_until < today_local():
        raise QuoteError("A validade já passou. Atualize a validade antes de enviar.")


def change_status(quote: Quote, target: QuoteStatus, user) -> Quote:
    if is_locked(quote):
        raise QuoteError("Este orçamento já gerou um projeto e não pode ser alterado.")
    if target == S.APPROVED:
        raise QuoteError("Use a ação de aprovar.")      # aprovação passa por approve()
    if target not in TRANSITIONS[quote.status]:
        raise QuoteError(f"Não é possível mudar de “{quote.status.label}” para “{target.label}”.")
    if target == S.SENT:
        _ensure_can_leave_draft(quote)
    quote.status = target
    log_activity("status", f"Orçamento de {quote.client.name}: {target.label.lower()}", user, "quote", quote.id)
    db.session.commit()
    return quote


def approve(quote: Quote, user, create_project: bool = False) -> Project | None:
    """Aprova e, opcionalmente, já cria o projeto — tudo na mesma transação."""
    if is_locked(quote):
        raise QuoteError("Este orçamento já gerou um projeto.")
    if S.APPROVED not in TRANSITIONS[quote.status]:
        raise QuoteError("Só é possível aprovar orçamentos enviados ou aguardando resposta.")
    if quote.price_cents <= 0:
        raise QuoteError("Defina o valor do orçamento antes de aprová-lo.")
    if create_project and quote.client.is_archived:       # valida ANTES de alterar qualquer coisa
        raise QuoteError("O cliente está arquivado. Restaure o cliente para criar o projeto.")
    try:
        quote.status = S.APPROVED
        log_activity("status", f"Orçamento de {quote.client.name}: aprovado", user, "quote", quote.id)
        project = _build_project(quote, user) if create_project else None
        db.session.commit()
    except Exception:
        db.session.rollback()                              # aprovação e projeto: tudo ou nada
        raise
    return project


def create_project_from_quote(quote: Quote, user) -> Project:
    """Cria o projeto de um orçamento já aprovado. Nunca duplica."""
    if quote.project_id:
        return quote.project
    if quote.status != S.APPROVED:
        raise QuoteError("Aprove o orçamento antes de criar o projeto.")
    project = _build_project(quote, user)
    db.session.commit()
    return project


def _build_project(quote: Quote, user) -> Project:
    if quote.client.is_archived:
        raise QuoteError("O cliente está arquivado. Restaure o cliente para criar o projeto.")
    first_line = (quote.description or "").strip().splitlines()[0] if (quote.description or "").strip() else ""
    project = Project(
        client_id=quote.client_id,
        name=(first_line[:150] or f"Orçamento #{quote.id}"),
        description=quote.description,
        style=quote.style,
        body_region_id=quote.body_region_id,
        size=quote.size,
        price_cents=quote.price_cents,
        notes=quote.notes,
        status=ProjectStatus.APPROVED,
    )
    db.session.add(project)
    db.session.flush()
    quote.project_id = project.id
    log_activity("created", f"Projeto criado a partir do orçamento de {quote.client.name}", user, "project", project.id)
    return project


def delete_quote(quote: Quote, user) -> None:
    if is_locked(quote):
        raise QuoteError("Este orçamento gerou um projeto e não pode ser excluído.")
    log_activity("deleted", f"Orçamento excluído: {quote.client.name}", user, "quote", quote.id)
    db.session.delete(quote)
    db.session.commit()


# ---------- Expiração automática ----------
EXPIRY_CHECK_INTERVAL = timedelta(hours=1)


def expire_overdue(force: bool = False) -> int:
    """Marca como 'expirado' os orçamentos abertos com validade vencida.
    Roda no máximo 1x por hora por processo (a menos que force=True)."""
    state = current_app.extensions.setdefault("quote_expiry", {"last": None})
    now = now_local()
    if not force and state["last"] and now - state["last"] < EXPIRY_CHECK_INTERVAL:
        return 0
    state["last"] = now

    overdue = (Quote.query.options(joinedload(Quote.client))
               .filter(Quote.status.in_(OPEN_STATUSES), Quote.valid_until.isnot(None),
                       Quote.valid_until < today_local()).all())
    for quote in overdue:
        quote.status = S.EXPIRED
        log_activity("status", f"Orçamento de {quote.client.name} expirou", None, "quote", quote.id)
    if overdue:
        db.session.commit()
    return len(overdue)


# ---------- Mensagem para WhatsApp ----------
def whatsapp_text(quote: Quote) -> str:
    """Texto do orçamento pronto para copiar. Não inclui observações internas."""
    first_name = quote.client.name.split()[0]
    lines = [f"Olá, {first_name}! Segue o orçamento da sua tatuagem no {studio_name()}:", ""]
    lines.append(f"• Projeto: {quote.description.strip()}")
    if quote.style:
        lines.append(f"• Estilo: {quote.style}")
    if quote.body_region:
        lines.append(f"• Região: {quote.body_region.name}")
    if quote.size:
        lines.append(f"• Tamanho: {quote.size}")
    lines.append(f"• Valor: {format_brl(quote.price_cents)}")
    if quote.valid_until:
        lines.append(f"• Válido até: {quote.valid_until:%d/%m/%Y}")
    lines += ["", "Qualquer dúvida, é só me chamar!"]
    return "\n".join(lines)
