from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.forms.settings import CategoryForm, PasswordForm, PreferencesForm, ProfileForm, ServiceForm, StudioForm
from app.models import Category, Service
from app.models.enums import CategoryKind
from app.services import settings_service as cfg
from app.services.activity_service import log_activity

bp = Blueprint("settings", __name__, url_prefix="/configuracoes")
GROUPS = {"financeiras": (CategoryKind.INCOME, CategoryKind.EXPENSE), "estoque": (CategoryKind.INVENTORY,)}


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


def _page(template, current, **ctx):
    return render_template(template, current=current, **ctx)


@bp.route("/", strict_slashes=False)
def index():
    return redirect(url_for("settings.profile"))


@bp.route("/perfil", methods=["GET", "POST"])
def profile():
    form = ProfileForm(obj=current_user, user=current_user)
    if form.validate_on_submit():
        current_user.name, current_user.email = form.name.data, form.email.data.lower()
        log_activity("updated", "Perfil atualizado", current_user, "user", current_user.id)
        db.session.commit()
        flash("Perfil atualizado.", "success")
        return redirect(url_for("settings.profile"))
    return _page("settings/profile.html", "perfil", form=form, pw=PasswordForm(user=current_user)), (400 if form.errors else 200)


@bp.route("/senha", methods=["POST"])
def password():
    pw = PasswordForm(user=current_user)
    if pw.validate_on_submit():
        current_user.set_password(pw.new.data)
        log_activity("updated", "Senha alterada", current_user, "user", current_user.id)
        db.session.commit()
        flash("Senha alterada com sucesso.", "success")
        return redirect(url_for("settings.profile"))
    return _page("settings/profile.html", "perfil", form=ProfileForm(obj=current_user, user=current_user), pw=pw), 400


def _kv_page(form_cls, keys, current, title, template="settings/form.html"):
    form = form_cls()
    if request.method == "GET":
        for k in keys:
            value = {"studio_name": cfg.studio_name(), "pref_quote_validity_days": cfg.quote_validity_days(),
                     "pref_default_duration": cfg.default_duration()}.get(k, cfg.get_setting(k, ""))
            getattr(form, k).data = value
    if form.validate_on_submit():
        for k in keys:
            cfg.set_setting(k, getattr(form, k).data)
        log_activity("updated", f"{title} atualizado(as)", current_user, "settings")
        db.session.commit()
        flash("Configurações salvas.", "success")
        return redirect(request.path)
    return _page(template, current, form=form, title=title), (400 if form.errors else 200)


@bp.route("/estudio", methods=["GET", "POST"])
def studio():
    return _kv_page(StudioForm, ["studio_name", "studio_phone", "studio_instagram", "studio_address"], "estudio", "Dados do estúdio")


@bp.route("/preferencias", methods=["GET", "POST"])
def preferences():
    return _kv_page(PreferencesForm, ["pref_quote_validity_days", "pref_default_duration"], "preferencias", "Preferências do sistema")


# ---------- Serviços ----------
@bp.route("/servicos", methods=["GET", "POST"])
def services():
    form = ServiceForm()
    if form.validate_on_submit():
        if Service.query.filter(db.func.lower(Service.name) == form.name.data.lower()).first():
            form.name.errors.append("Já existe um serviço com este nome.")
        else:
            db.session.add(Service(name=form.name.data, default_duration_minutes=form.default_duration_minutes.data,
                                   default_price_cents=form.default_price_cents.data or 0, is_active=form.is_active.data))
            db.session.commit()
            flash("Serviço adicionado.", "success")
            return redirect(url_for("settings.services"))
    return _page("settings/services.html", "servicos", form=form, items=Service.query.order_by(Service.name).all()), (400 if form.errors else 200)


@bp.route("/servicos/<int:item_id>/editar", methods=["GET", "POST"])
def service_edit(item_id):
    item = db.get_or_404(Service, item_id)
    form = ServiceForm(obj=item)
    if form.validate_on_submit():
        clash = Service.query.filter(db.func.lower(Service.name) == form.name.data.lower(), Service.id != item.id).first()
        if clash:
            form.name.errors.append("Já existe um serviço com este nome.")
        else:
            item.name, item.default_duration_minutes = form.name.data, form.default_duration_minutes.data
            item.default_price_cents, item.is_active = form.default_price_cents.data or 0, form.is_active.data
            db.session.commit()
            flash("Serviço atualizado.", "success")
            return redirect(url_for("settings.services"))
    return _page("settings/form.html", "servicos", form=form, title="Editar serviço"), (400 if form.errors else 200)


# ---------- Categorias ----------
@bp.route("/categorias/<group>", methods=["GET", "POST"])
def categories(group):
    if group not in GROUPS:
        return render_template("errors/error.html", code=404, title="Página não encontrada", message="O endereço solicitado não existe."), 404
    kinds = GROUPS[group]
    form = CategoryForm()
    if group == "estoque":
        del form.kind
    if form.validate_on_submit():
        kind = kinds[0] if group == "estoque" else CategoryKind(form.kind.data)
        if Category.query.filter(Category.kind == kind, db.func.lower(Category.name) == form.name.data.lower()).first():
            form.name.errors.append("Já existe uma categoria com este nome.")
        else:
            db.session.add(Category(kind=kind, name=form.name.data, is_active=form.is_active.data))
            db.session.commit()
            flash("Categoria adicionada.", "success")
            return redirect(url_for("settings.categories", group=group))
    items = Category.query.filter(Category.kind.in_(kinds)).order_by(Category.kind, Category.name).all()
    return _page("settings/categories.html", "cat-" + group, form=form, items=items, group=group), (400 if form.errors else 200)


@bp.route("/categorias/<int:item_id>/editar", methods=["GET", "POST"])
def category_edit(item_id):
    item = db.get_or_404(Category, item_id)
    group = "estoque" if item.kind == CategoryKind.INVENTORY else "financeiras"
    form = CategoryForm(obj=item)
    del form.kind
    if form.validate_on_submit():
        clash = Category.query.filter(Category.kind == item.kind, db.func.lower(Category.name) == form.name.data.lower(), Category.id != item.id).first()
        if clash:
            form.name.errors.append("Já existe uma categoria com este nome.")
        else:
            item.name, item.is_active = form.name.data, form.is_active.data
            db.session.commit()
            flash("Categoria atualizada.", "success")
            return redirect(url_for("settings.categories", group=group))
    return _page("settings/form.html", "cat-" + group, form=form, title="Editar categoria"), (400 if form.errors else 200)
