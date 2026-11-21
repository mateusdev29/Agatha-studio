"""Regras da Anamnese. DADO SENSÍVEL: nunca vai para logs, dashboards ou gráficos."""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import AnamnesisResponse as R, AnamnesisTemplate as Q, Client
from app.models.base import utcnow
from app.models.enums import FieldType as FT
from app.services.activity_service import log_activity

PER_PAGE = 15
MAX_TEXT = 3000


def active_questions():
    return Q.query.filter_by(is_active=True).order_by(Q.position, Q.id).all()


def parse_answers(questions, form) -> tuple[list, dict]:
    """Valida cada resposta conforme o tipo. Retorna (snapshot, erros_por_id)."""
    answers, errors = [], {}
    for q in questions:
        key = f"q_{q.id}"
        t = q.field_type
        if t == FT.CHECKBOX:
            value = form.getlist(key)
            if any(v not in (q.options or []) for v in value):
                errors[q.id] = "Opção inválida."
        else:
            value = (form.get(key) or "").strip()
            if value and t in (FT.RADIO, FT.SELECT) and value not in (q.options or []):
                errors[q.id] = "Opção inválida."
            elif value and t == FT.DATE:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    errors[q.id] = "Data inválida."
            elif len(value) > MAX_TEXT:
                errors[q.id] = f"Use até {MAX_TEXT} caracteres."
        if q.required and not value and q.id not in errors:
            errors[q.id] = "Resposta obrigatória."
        answers.append({"id": q.id, "label": q.label, "type": t.value, "value": value})
    return answers, errors


def create_response(client: Client, answers: list, signature_name: str, user) -> R:
    now = utcnow()
    response = R(client_id=client.id, answers=answers, accepted=True, accepted_at=now, signature_name=signature_name)
    db.session.add(response)
    db.session.flush()
    log_activity("created", f"Ficha de anamnese registrada: {client.name}", user, "anamnesis", response.id)   # sem conteúdo
    db.session.commit()
    return response


def search_responses(q="", page=1):
    stmt = db.select(R).join(Client).options(joinedload(R.client))
    q = (q or "").strip()
    if q:
        stmt = stmt.where(Client.name.ilike("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    return db.paginate(stmt.order_by(R.created_at.desc(), R.id.desc()), page=page, per_page=PER_PAGE, error_out=False)


def save_question(question, form, user):
    creating = question is None
    question = question or Q()
    question.label, question.help_text, question.field_type = form.label.data, form.help_text.data or None, FT(form.field_type.data)
    question.options = form.parsed_options() if form.field_type.data in {"checkbox", "radio", "select"} else None
    question.position, question.required, question.is_active = form.position.data, form.required.data, form.is_active.data
    db.session.add(question)
    db.session.flush()
    log_activity("created" if creating else "updated", f"Pergunta da anamnese {'criada' if creating else 'atualizada'}", user, "anamnesis_question", question.id)
    db.session.commit()
    return question


def format_value(answer: dict) -> str:
    value = answer.get("value")
    if isinstance(value, list):
        return ", ".join(value) or "—"
    if answer.get("type") == FT.DATE.value and value:
        try:
            return date.fromisoformat(value).strftime("%d/%m/%Y")
        except ValueError:
            return value
    return value or "—"
