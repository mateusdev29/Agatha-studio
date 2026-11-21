from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.finance import TransactionForm
from app.models import FinancialTransaction as T
from app.models.enums import TransactionStatus, TransactionType
from app.services import finance_service as svc
from app.utils.dates import today_local
from app.utils.periods import parse_period
from app.utils.security import is_safe_redirect_url

bp = Blueprint("finance", __name__, url_prefix="/financeiro")
TABS = [("todos", "Lançamentos"), ("receitas", "Receitas"), ("despesas", "Despesas"), ("pagamentos", "Pagamentos"), ("categorias", "Categorias")]
KINDS = {"receitas": TransactionType.INCOME, "despesas": TransactionType.EXPENSE}


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


@bp.route("/", strict_slashes=False)
def index():
    tab = request.args.get("aba", "todos")
    tab = tab if tab in dict(TABS) else "todos"
    period, status, q = parse_period(request.args), request.args.get("status", ""), request.args.get("q", "").strip()
    ctx = {"tab": tab, "tabs": TABS, "period": period, "status": status, "q": q, "summary": svc.summary(period), "statuses": TransactionStatus}
    if tab == "categorias":
        ctx["breakdown"] = svc.category_breakdown(period)
    else:
        ctx["items"] = svc.search(tab, status, q, period, request.args.get("page", 1, type=int))
    return render_template("finance/index.html", **ctx)


@bp.route("/<kind>/nova", methods=["GET", "POST"])
def create(kind):
    if kind not in KINDS:
        return render_template("errors/error.html", code=404, title="Página não encontrada", message="O endereço solicitado não existe."), 404
    form = TransactionForm(kind=KINDS[kind])
    if request.method == "GET":
        form.date.data = today_local()
        if kind == "receitas" and request.args.get("cliente", type=int) in [choice.value for choice in form.client_id.choices]:
            form.client_id.data = request.args.get("cliente", type=int)
    if form.validate_on_submit():
        svc.save(None, form.cleaned(), current_user)
        flash("Lançamento registrado.", "success")
        return redirect(url_for("finance.index", aba=kind))
    return render_template("finance/form.html", form=form, item=None, kind=KINDS[kind]), (400 if form.errors else 200)


@bp.route("/<int:item_id>/editar", methods=["GET", "POST"])
def edit(item_id):
    item = db.get_or_404(T, item_id)
    form = TransactionForm(obj=item, kind=item.type, current=item)
    if request.method == "GET":
        form.category_id.data = item.category_id or 0
        if "client_id" in form:                                   # despesas não têm cliente/projeto
            form.client_id.data, form.project_id.data = item.client_id or 0, item.project_id or 0
        form.status.data = item.status.value
        form.payment_method.data = item.payment_method.value if item.payment_method else ""
    if form.validate_on_submit():
        svc.save(item, form.cleaned(), current_user)
        flash("Lançamento atualizado.", "success")
        return redirect(url_for("finance.index", aba="receitas" if item.type == TransactionType.INCOME else "despesas"))
    return render_template("finance/form.html", form=form, item=item, kind=item.type), (400 if form.errors else 200)


@bp.route("/<int:item_id>/pagar", methods=["POST"])
def pay(item_id):
    item = db.get_or_404(T, item_id)
    try:
        svc.mark_paid(item, current_user)
        flash("Marcado como pago.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(request.referrer if is_safe_redirect_url(request.referrer) else url_for("finance.index"))


@bp.route("/<int:item_id>/excluir", methods=["POST"])
def delete(item_id):
    item = db.get_or_404(T, item_id)
    svc.delete(item, current_user)
    flash("Lançamento excluído.", "info")
    return redirect(url_for("finance.index"))
