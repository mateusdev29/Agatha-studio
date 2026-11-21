from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.stock import ItemForm, MovementForm
from app.models import Category, InventoryItem as Item
from app.models.enums import CategoryKind, MovementType
from app.services import stock_service as svc

bp = Blueprint("stock", __name__, url_prefix="/estoque")


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


def _back(item):
    return redirect(url_for("stock.detail", item_id=item.id))


@bp.route("/", strict_slashes=False)
def index():
    tab = "movimentacoes" if request.args.get("aba") == "movimentacoes" else "itens"
    page = request.args.get("page", 1, type=int)
    ctx = {"tab": tab, "low_count": svc.low_stock_count()}
    if tab == "movimentacoes":
        ctx["movements"] = svc.search_movements(page)
    else:
        q, cat = request.args.get("q", "").strip(), request.args.get("categoria", type=int)
        low, archived = request.args.get("baixo") == "1", request.args.get("status") == "arquivados"
        ctx.update(items=svc.search_items(q, cat, low, not archived, page), q=q, categoria=cat, low=low, archived=archived,
                   categories=Category.query.filter_by(kind=CategoryKind.INVENTORY).order_by(Category.name).all())
    return render_template("stock/index.html", **ctx)


@bp.route("/novo", methods=["GET", "POST"])
def create():
    form = ItemForm()
    if form.validate_on_submit():
        item = svc.create_item(form.cleaned(), form.quantity.data or 0, current_user)
        flash("Produto cadastrado.", "success")
        return _back(item)
    return render_template("stock/form.html", form=form, item=None), (400 if form.errors else 200)


@bp.route("/<int:item_id>")
def detail(item_id):
    item = db.get_or_404(Item, item_id)
    return render_template("stock/detail.html", item=item, form=MovementForm(), types=MovementType,
                           history=svc.search_movements(request.args.get("page", 1, type=int), item.id))


@bp.route("/<int:item_id>/editar", methods=["GET", "POST"])
def edit(item_id):
    item = db.get_or_404(Item, item_id)
    form = ItemForm(obj=item, editing=True)
    if request.method == "GET":
        form.category_id.data = item.category_id or 0
    if form.validate_on_submit():
        svc.update_item(item, form.cleaned(), current_user)
        flash("Produto atualizado.", "success")
        return _back(item)
    return render_template("stock/form.html", form=form, item=item), (400 if form.errors else 200)


@bp.route("/<int:item_id>/movimentar", methods=["POST"])
def move(item_id):
    item = db.get_or_404(Item, item_id)
    form = MovementForm()
    if not form.validate_on_submit():
        flash(next((e for errs in form.errors.values() for e in errs), "Dados inválidos."), "error")
        return _back(item)
    try:
        svc.move(item, MovementType(form.type.data), form.quantity.data, form.reason.data, current_user)
        flash("Movimentação registrada.", "success")
    except svc.StockError as exc:
        flash(str(exc), "error")
    return _back(item)


@bp.route("/<int:item_id>/arquivar", methods=["POST"])
def archive(item_id):
    item = db.get_or_404(Item, item_id)
    svc.set_active(item, False, current_user)
    flash("Produto arquivado. O histórico foi preservado.", "info")
    return redirect(url_for("stock.index"))


@bp.route("/<int:item_id>/restaurar", methods=["POST"])
def restore(item_id):
    item = db.get_or_404(Item, item_id)
    svc.set_active(item, True, current_user)
    flash("Produto restaurado.", "success")
    return _back(item)
