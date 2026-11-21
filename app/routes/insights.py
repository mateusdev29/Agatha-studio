"""Satisfação, Preferências Corporais e Dashboard (leitura analítica)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.forms.evaluations import EvaluationForm
from app.models import Evaluation
from app.services import analytics_service as an
from app.services.activity_service import log_activity
from app.utils.dates import today_local
from app.utils.periods import parse_period

satisfaction_bp = Blueprint("satisfaction", __name__, url_prefix="/satisfacao")
body_bp = Blueprint("body", __name__, url_prefix="/preferencias-corporais")
dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _guard():
    """Todas as rotas exigem autenticação."""


for _bp in (satisfaction_bp, body_bp, dashboard_bp):
    _bp.before_request(login_required(_guard))


# ---------- Dashboard ----------
@dashboard_bp.route("/", strict_slashes=False)
def dashboard():
    period = parse_period(request.args, default="mes")
    money = an.monthly_money(period)
    styles = an.projects_by_style(period)
    regions = [r for r in an.projects_by_region(period) if r["count"]][:8]
    sources = an.clients_by_source(period)
    charts = {
        "revenue": {"type": "bar", "money": True, "labels": money["labels"], "datasets": [{"label": "Faturamento", "data": money["income"]}]},
        "income_expense": {"type": "bar", "money": True, "labels": money["labels"],
                           "datasets": [{"label": "Receitas", "data": money["income"]}, {"label": "Despesas", "data": money["expense"]}]},
        "styles": {"type": "bar", "horizontal": True, "labels": styles["labels"], "datasets": [{"label": "Projetos", "data": styles["values"]}]},
        "regions": {"type": "bar", "horizontal": True, "labels": [r["name"] for r in regions],
                    "datasets": [{"label": "Projetos", "data": [r["count"] for r in regions]}]},
        "sources": {"type": "doughnut", "labels": sources["labels"], "datasets": [{"label": "Clientes", "data": sources["values"]}]},
    }
    has = {"money": any(money["income"]) or any(money["expense"]), "styles": bool(styles["labels"]),
           "regions": bool(regions), "sources": bool(sources["labels"])}
    return render_template("dashboard/index.html", period=period, ind=an.indicators(period), charts=charts, has=has)


# ---------- Preferências corporais ----------
@body_bp.route("/", strict_slashes=False)
def body_map():
    period = parse_period(request.args, default="tudo")
    regions = an.projects_by_region(period)
    top = max((r["count"] for r in regions), default=0)
    heat = {r["slug"]: an.heat_level(r["count"], top) for r in regions}
    counts = {r["slug"]: r["count"] for r in regions}
    ranking = [r for r in regions if r["count"]]
    chart = {"type": "bar", "horizontal": True, "labels": [r["name"] for r in ranking], "datasets": [{"label": "Projetos", "data": [r["count"] for r in ranking]}]}
    names = {r["slug"]: r["name"] for r in regions}
    return render_template("body/index.html", period=period, regions=regions, heat=heat, counts=counts, names=names, chart=chart,
                           ranking=ranking, styles=an.styles_by_region(period), total=sum(counts.values()))


# ---------- Satisfação ----------
@satisfaction_bp.route("/", strict_slashes=False)
def index():
    period = parse_period(request.args, default="ano")
    page = request.args.get("page", 1, type=int)
    stmt = db.select(Evaluation).options(joinedload(Evaluation.client)).where(Evaluation.evaluated_on >= period.start, Evaluation.evaluated_on <= period.end)
    items = db.paginate(stmt.order_by(Evaluation.evaluated_on.desc(), Evaluation.id.desc()), page=page, per_page=15, error_out=False)
    ind = an.indicators(period)
    dist, trend = an.score_distribution(period), an.score_by_month(period)
    charts = {"dist": {"type": "bar", "labels": dist["labels"], "datasets": [{"label": "Avaliações", "data": dist["values"]}]},
              "trend": {"type": "line", "labels": trend["labels"], "datasets": [{"label": "Nota média", "data": trend["values"]}], "max": 10}}
    return render_template("satisfaction/index.html", period=period, items=items, ind=ind, charts=charts, has=ind.evaluations > 0,
                           min_nps=an.MIN_NPS_RESPONSES)


def _form_page(form, evaluation):
    return render_template("satisfaction/form.html", form=form, item=evaluation), (400 if form.errors else 200)


@satisfaction_bp.route("/nova", methods=["GET", "POST"])
def create():
    form = EvaluationForm()
    if request.method == "GET":
        form.evaluated_on.data = today_local()
        cid = request.args.get("cliente", type=int)
        if cid and any(cid == c for c, _ in form.client_id.choices):
            form.client_id.data = cid
    if form.validate_on_submit():
        ev = Evaluation(**form.cleaned())
        db.session.add(ev)
        db.session.flush()
        log_activity("created", f"Avaliação registrada: nota {ev.score}", current_user, "evaluation", ev.id)
        db.session.commit()
        flash("Avaliação registrada.", "success")
        return redirect(url_for("satisfaction.index"))
    return _form_page(form, None)


@satisfaction_bp.route("/<int:item_id>/editar", methods=["GET", "POST"])
def edit(item_id):
    ev = db.get_or_404(Evaluation, item_id)
    form = EvaluationForm(obj=ev, current=ev)
    if request.method == "GET":
        form.appointment_id.data = ev.appointment_id or 0
    if form.validate_on_submit():
        for k, v in form.cleaned().items():
            setattr(ev, k, v)
        log_activity("updated", f"Avaliação atualizada: nota {ev.score}", current_user, "evaluation", ev.id)
        db.session.commit()
        flash("Avaliação atualizada.", "success")
        return redirect(url_for("satisfaction.index"))
    return _form_page(form, ev)


@satisfaction_bp.route("/<int:item_id>/excluir", methods=["POST"])
def delete(item_id):
    ev = db.get_or_404(Evaluation, item_id)
    log_activity("deleted", "Avaliação excluída", current_user, "evaluation", ev.id)
    db.session.delete(ev)
    db.session.commit()
    flash("Avaliação excluída.", "info")
    return redirect(url_for("satisfaction.index"))
