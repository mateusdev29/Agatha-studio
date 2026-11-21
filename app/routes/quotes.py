from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.quotes import QuoteForm
from app.models import Quote
from app.models.enums import QuoteStatus
from app.services import quote_service as svc
from app.services.settings_service import quote_validity_days
from app.utils.dates import today_local

bp = Blueprint("quotes", __name__, url_prefix="/orcamentos")


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


def _get_quote(quote_id) -> Quote:
    return db.get_or_404(Quote, quote_id)


def _back(quote):
    return redirect(url_for("quotes.detail", quote_id=quote.id))


@bp.route("/", strict_slashes=False)
def index():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    quotes = svc.search_quotes(q, status, request.args.get("page", 1, type=int))
    return render_template("quotes/list.html", quotes=quotes, q=q, status=status, statuses=QuoteStatus)


@bp.route("/novo", methods=["GET", "POST"])
def create():
    form = QuoteForm()
    if request.method == "GET":
        preselected = request.args.get("cliente", type=int)
        if preselected and any(preselected == c for c, _ in form.client_id.choices):
            form.client_id.data = preselected
        form.valid_until.data = today_local() + timedelta(days=quote_validity_days())
    if form.validate_on_submit():
        quote = svc.create_quote(form.cleaned(), current_user)
        flash("Orçamento criado como rascunho.", "success")
        return _back(quote)
    return render_template("quotes/form.html", form=form, quote=None), (400 if form.errors else 200)


@bp.route("/<int:quote_id>")
def detail(quote_id):
    quote = _get_quote(quote_id)
    return render_template("quotes/detail.html", quote=quote, locked=svc.is_locked(quote),
                           message=svc.whatsapp_text(quote), S=QuoteStatus)


@bp.route("/<int:quote_id>/editar", methods=["GET", "POST"])
def edit(quote_id):
    quote = _get_quote(quote_id)
    if svc.is_locked(quote):
        flash("Este orçamento já gerou um projeto e não pode mais ser editado.", "error")
        return _back(quote)
    form = QuoteForm(obj=quote, current_client_id=quote.client_id, original_valid_until=quote.valid_until)
    if request.method == "GET":
        form.body_region_id.data = quote.body_region_id or 0
    if form.validate_on_submit():
        svc.update_quote(quote, form.cleaned(), current_user)
        flash("Orçamento atualizado.", "success")
        return _back(quote)
    return render_template("quotes/form.html", form=form, quote=quote), (400 if form.errors else 200)


def _run(quote, action, success):
    try:
        result = action()
        flash(success, "success")
        return result
    except svc.QuoteError as exc:
        flash(str(exc), "error")


@bp.route("/<int:quote_id>/status", methods=["POST"])
def change_status(quote_id):
    quote = _get_quote(quote_id)
    try:
        target = QuoteStatus(request.form.get("status", ""))
    except ValueError:
        flash("Status inválido.", "error")
        return _back(quote)
    _run(quote, lambda: svc.change_status(quote, target, current_user), f"Orçamento marcado como {target.label.lower()}.")
    return _back(quote)


@bp.route("/<int:quote_id>/aprovar", methods=["POST"])
def approve(quote_id):
    quote = _get_quote(quote_id)
    create = request.form.get("create_project") == "1"
    try:
        project = svc.approve(quote, current_user, create_project=create)
    except svc.QuoteError as exc:
        flash(str(exc), "error")
        return _back(quote)
    if project:
        flash("Orçamento aprovado e projeto criado.", "success")
        return redirect(url_for("projects.detail", project_id=project.id))
    flash("Orçamento aprovado.", "success")
    return _back(quote)


@bp.route("/<int:quote_id>/criar-projeto", methods=["POST"])
def create_project(quote_id):
    quote = _get_quote(quote_id)
    try:
        project = svc.create_project_from_quote(quote, current_user)
    except svc.QuoteError as exc:
        flash(str(exc), "error")
        return _back(quote)
    flash("Projeto criado a partir do orçamento.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.route("/<int:quote_id>/excluir", methods=["POST"])
def delete(quote_id):
    quote = _get_quote(quote_id)
    try:
        svc.delete_quote(quote, current_user)
    except svc.QuoteError as exc:
        flash(str(exc), "error")
        return _back(quote)
    flash("Orçamento excluído.", "info")
    return redirect(url_for("quotes.index"))
