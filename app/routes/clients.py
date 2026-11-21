from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.clients import ClientForm
from app.models import Client
from app.services import client_service as svc

bp = Blueprint("clients", __name__, url_prefix="/clientes")

TABS = [
    ("resumo", "Resumo"), ("projetos", "Projetos"), ("agenda", "Agenda"), ("orcamentos", "Orçamentos"),
    ("pagamentos", "Pagamentos"), ("anamnese", "Anamnese"), ("avaliacoes", "Avaliações"),
    ("observacoes", "Observações"),
]


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


@bp.route("/", strict_slashes=False)
def index():
    status = request.args.get("status", "ativos")
    if status not in svc.STATUS_FILTERS:
        status = "ativos"
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    clients = svc.search_clients(q, status, page)
    return render_template("clients/list.html", clients=clients, q=q, status=status)


@bp.route("/novo", methods=["GET", "POST"])
def create():
    form = ClientForm()
    if form.validate_on_submit():
        client = svc.create_client(form.cleaned(), current_user)
        flash("Cliente cadastrado com sucesso.", "success")
        return redirect(url_for("clients.detail", client_id=client.id))
    return render_template("clients/form.html", form=form, client=None), (400 if form.errors else 200)


@bp.route("/<int:client_id>")
def detail(client_id):
    client = db.get_or_404(Client, client_id)
    tab = request.args.get("aba", "resumo")
    if tab not in dict(TABS):
        tab = "resumo"
    context = {"client": client, "tab": tab, "tabs": TABS}
    if tab == "resumo":
        context.update(summary=svc.client_summary(client), history=svc.client_history(client))
    else:
        context["items"] = svc.tab_items(client, tab)
    return render_template("clients/detail.html", **context)


@bp.route("/<int:client_id>/editar", methods=["GET", "POST"])
def edit(client_id):
    client = db.get_or_404(Client, client_id)
    form = ClientForm(obj=client)
    if form.validate_on_submit():
        svc.update_client(client, form.cleaned(), current_user)
        flash("Dados do cliente atualizados.", "success")
        return redirect(url_for("clients.detail", client_id=client.id))
    return render_template("clients/form.html", form=form, client=client), (400 if form.errors else 200)


@bp.route("/<int:client_id>/arquivar", methods=["POST"])
def archive(client_id):
    client = db.get_or_404(Client, client_id)
    svc.archive_client(client, current_user)
    flash(f"{client.name} foi arquivado. O histórico foi preservado.", "info")
    return redirect(url_for("clients.index"))


@bp.route("/<int:client_id>/restaurar", methods=["POST"])
def restore(client_id):
    client = db.get_or_404(Client, client_id)
    svc.restore_client(client, current_user)
    flash(f"{client.name} foi restaurado.", "success")
    return redirect(url_for("clients.detail", client_id=client.id))
