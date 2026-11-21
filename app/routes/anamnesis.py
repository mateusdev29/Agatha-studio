from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.anamnesis import FillForm, QuestionForm
from app.models import AnamnesisResponse, AnamnesisTemplate, Client
from app.services import anamnesis_service as svc

bp = Blueprint("anamnesis", __name__, url_prefix="/anamnese")


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


@bp.route("/", strict_slashes=False)
def index():
    q = request.args.get("q", "").strip()
    return render_template("anamnesis/index.html", responses=svc.search_responses(q, request.args.get("page", 1, type=int)), q=q)


@bp.route("/nova", methods=["GET", "POST"])
def fill():
    form, questions = FillForm(), svc.active_questions()
    answers, errors = [], {}
    if request.method == "GET":
        cid = request.args.get("cliente", type=int)
        if cid and any(cid == choice.value for choice in form.client_id.choices):
            form.client_id.data = cid
    else:
        answers, errors = svc.parse_answers(questions, request.form)
        if form.validate_on_submit() and not errors:
            client = db.session.get(Client, form.client_id.data)
            response = svc.create_response(client, answers, form.signature_name.data, current_user)
            flash("Ficha de anamnese registrada.", "success")
            return redirect(url_for("anamnesis.detail", response_id=response.id))
    given = {a["id"]: a["value"] for a in answers}
    return render_template("anamnesis/fill.html", form=form, questions=questions, errors=errors, given=given), (400 if (form.errors or errors) else 200)


@bp.route("/<int:response_id>")
def detail(response_id):
    response = db.get_or_404(AnamnesisResponse, response_id)
    resp = make_response(render_template("anamnesis/detail.html", r=response, fmt=svc.format_value))
    resp.headers["Cache-Control"] = "no-store"       # dado de saúde: nada de cache no navegador/proxy
    return resp


# ---------- Perguntas configuráveis ----------
@bp.route("/perguntas", methods=["GET", "POST"])
def questions():
    form = QuestionForm()
    if request.method == "GET":
        form.position.data = (db.session.query(db.func.coalesce(db.func.max(AnamnesisTemplate.position), 0)).scalar() or 0) + 1
    if form.validate_on_submit():
        svc.save_question(None, form, current_user)
        flash("Pergunta adicionada.", "success")
        return redirect(url_for("anamnesis.questions"))
    items = AnamnesisTemplate.query.order_by(AnamnesisTemplate.position, AnamnesisTemplate.id).all()
    return render_template("anamnesis/questions.html", form=form, items=items), (400 if form.errors else 200)


@bp.route("/perguntas/<int:item_id>/editar", methods=["GET", "POST"])
def question_edit(item_id):
    item = db.get_or_404(AnamnesisTemplate, item_id)
    form = QuestionForm(obj=item)
    if request.method == "GET":
        form.field_type.data, form.options_text.data = item.field_type.value, "\n".join(item.options or [])
    if form.validate_on_submit():
        svc.save_question(item, form, current_user)
        flash("Pergunta atualizada. Fichas já preenchidas não mudam.", "success")
        return redirect(url_for("anamnesis.questions"))
    return render_template("settings/form.html", form=form, title="Editar pergunta", current="anamnese"), (400 if form.errors else 200)
