"""Indicadores do Dashboard, da Satisfação e do mapa corporal. Tudo calculado do banco.

Definições (documentadas porque indicadores ambíguos enganam):
- Faturamento: receitas PAGAS no período. Despesas: despesas PAGAS no período. Lucro = faturamento - despesas.
- Ticket médio: faturamento ÷ atendimentos REALIZADOS no período (sem atendimentos: sem valor).
- Clientes: clientes ativos (não arquivados). Novos: cadastrados no período.
- Recorrentes: clientes com atendimento realizado no período e ao menos 2 realizados até o fim do período.
- NPS: %promotores (9-10) - %detratores (0-6); só é calculado com MIN_NPS_RESPONSES avaliações.
- Estilos/regiões/origem: projetos (exceto cancelados) e clientes cadastrados no período.
Dados de anamnese (saúde) NUNCA entram aqui.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import Appointment, BodyRegion, Client, Evaluation, FinancialTransaction as T, Project
from app.models.enums import AppointmentStatus, ProjectStatus, TransactionStatus, TransactionType
from app.utils.dates import today_local
from app.utils.formatting import MONTHS

MIN_NPS_RESPONSES = 5
MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def month_range(period, max_months=12):
    """Primeiros dias dos meses a exibir nos gráficos (no máximo `max_months`, terminando no fim do período ou hoje)."""
    today = today_local()
    end = min(period.end, today)
    cursor = max(period.start.replace(day=1), (end.replace(day=1) - timedelta(days=31 * (max_months - 1))).replace(day=1))
    months = []
    while cursor <= end:
        months.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return months[-max_months:]


def month_label(d: date) -> str:
    return f"{MONTHS_SHORT[d.month - 1]}/{str(d.year)[2:]}"


def monthly_money(period):
    """{'labels': [...], 'income': [centavos], 'expense': [centavos]} por mês (apenas pagos)."""
    months = month_range(period)
    if not months:
        return {"labels": [], "income": [], "expense": []}
    lo, hi = max(months[0], period.start), min(period.end, today_local())
    rows = db.session.query(T.type, T.date, T.amount_cents).filter(
        T.status == TransactionStatus.PAID, T.date >= lo, T.date <= hi).all()
    sums = defaultdict(int)
    for kind, d, cents in rows:
        sums[(kind, d.year, d.month)] += cents
    return {"labels": [month_label(m) for m in months],
            "income": [sums[(TransactionType.INCOME, m.year, m.month)] for m in months],
            "expense": [sums[(TransactionType.EXPENSE, m.year, m.month)] for m in months]}


def nps(scores):
    """None se houver menos de MIN_NPS_RESPONSES respostas."""
    if len(scores) < MIN_NPS_RESPONSES:
        return None
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round((promoters - detractors) * 100 / len(scores))


@dataclass
class Indicators:
    income: int
    expense: int
    ticket: int | None
    clients_total: int
    clients_new: int
    clients_recurring: int
    projects_created: int
    projects_in_progress: int
    evaluations: int
    average_score: float | None
    nps: int | None

    @property
    def profit(self):
        return self.income - self.expense


def _paid(kind, period):
    return db.session.query(func.coalesce(func.sum(T.amount_cents), 0)).filter(
        T.type == kind, T.status == TransactionStatus.PAID, T.date >= period.start, T.date <= period.end).scalar()


def _bounds(period):
    return datetime.combine(period.start, time.min), datetime.combine(period.end + timedelta(days=1), time.min)


def indicators(period) -> Indicators:
    lo, hi = _bounds(period)
    income, expense = _paid(TransactionType.INCOME, period), _paid(TransactionType.EXPENSE, period)
    done_in_period = (db.session.query(Appointment.client_id, func.count())
                      .filter(Appointment.status == AppointmentStatus.DONE, Appointment.starts_at >= lo, Appointment.starts_at < hi)
                      .group_by(Appointment.client_id).all())
    done_count = sum(n for _, n in done_in_period)
    ids = [cid for cid, _ in done_in_period]
    recurring = 0
    if ids:
        totals = dict(db.session.query(Appointment.client_id, func.count()).filter(
            Appointment.status == AppointmentStatus.DONE, Appointment.starts_at < hi, Appointment.client_id.in_(ids))
            .group_by(Appointment.client_id).all())
        recurring = sum(1 for cid in ids if totals.get(cid, 0) >= 2)
    scores = [s for (s,) in db.session.query(Evaluation.score).filter(Evaluation.evaluated_on >= period.start, Evaluation.evaluated_on <= period.end)]
    return Indicators(
        income=income, expense=expense, ticket=round(income / done_count) if done_count else None,
        clients_total=Client.query.filter(Client.archived_at.is_(None)).count(),
        clients_new=Client.query.filter(Client.created_at >= lo, Client.created_at < hi).count(),
        clients_recurring=recurring,
        projects_created=Project.query.filter(Project.created_at >= lo, Project.created_at < hi, Project.status != ProjectStatus.CANCELED).count(),
        projects_in_progress=Project.query.filter(Project.status == ProjectStatus.IN_PROGRESS).count(),
        evaluations=len(scores), average_score=round(sum(scores) / len(scores), 1) if scores else None, nps=nps(scores))


def _top(counter: Counter, limit=8):
    items = counter.most_common(limit)
    return {"labels": [k for k, _ in items], "values": [v for _, v in items]}


def projects_by_style(period):
    lo, hi = _bounds(period)
    rows = db.session.query(Project.style, func.count()).filter(
        Project.created_at >= lo, Project.created_at < hi, Project.status != ProjectStatus.CANCELED,
        Project.style.isnot(None)).group_by(Project.style).all()
    return _top(Counter(dict(rows)))


def projects_by_region(period=None):
    """Quantidade de projetos (exceto cancelados) por região, incluindo as sem projetos (zero)."""
    q = db.session.query(BodyRegion.slug, BodyRegion.name, func.count(Project.id)).outerjoin(
        Project, (Project.body_region_id == BodyRegion.id) & (Project.status != ProjectStatus.CANCELED)
        & ((Project.created_at >= _bounds(period)[0]) & (Project.created_at < _bounds(period)[1]) if period else True)
    ).group_by(BodyRegion.id).order_by(func.count(Project.id).desc(), BodyRegion.position)
    return [{"slug": s, "name": n, "count": c} for s, n, c in q.all()]


def styles_by_region(period=None):
    """{slug: [(estilo, qtd), ...]} — estilos mais comuns em cada região."""
    q = db.session.query(BodyRegion.slug, Project.style, func.count()).join(Project, Project.body_region_id == BodyRegion.id).filter(
        Project.status != ProjectStatus.CANCELED, Project.style.isnot(None))
    if period:
        lo, hi = _bounds(period)
        q = q.filter(Project.created_at >= lo, Project.created_at < hi)
    out = defaultdict(list)
    for slug, style, n in q.group_by(BodyRegion.slug, Project.style).order_by(func.count().desc()).all():
        out[slug].append((style, n))
    return out


def clients_by_source(period):
    lo, hi = _bounds(period)
    rows = db.session.query(func.coalesce(Client.source, "Não informado"), func.count()).filter(
        Client.created_at >= lo, Client.created_at < hi).group_by(Client.source).all()
    return _top(Counter(dict(rows)))


def score_distribution(period):
    rows = dict(db.session.query(Evaluation.score, func.count()).filter(
        Evaluation.evaluated_on >= period.start, Evaluation.evaluated_on <= period.end).group_by(Evaluation.score).all())
    return {"labels": [str(i) for i in range(11)], "values": [rows.get(i, 0) for i in range(11)]}


def score_by_month(period):
    months = month_range(period)
    rows = db.session.query(Evaluation.evaluated_on, Evaluation.score).filter(
        Evaluation.evaluated_on >= period.start, Evaluation.evaluated_on <= period.end).all()
    acc = defaultdict(list)
    for d, s in rows:
        acc[(d.year, d.month)].append(s)
    labels = [month_label(m) for m in months]
    return {"labels": labels, "values": [round(sum(acc[(m.year, m.month)]) / len(acc[(m.year, m.month)]), 1) if acc[(m.year, m.month)] else None for m in months]}


def heat_level(count: int, maximum: int) -> int:
    """0 (sem dados) a 5 para colorir o mapa corporal."""
    if count <= 0 or maximum <= 0:
        return 0
    return max(1, min(5, -(-count * 5 // maximum)))
