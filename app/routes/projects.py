from flask import Blueprint, abort, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.projects import ProjectForm, ReferenceUploadForm, SessionForm
from app.models import Client, Project, ProjectReference, ProjectSession
from app.models.enums import ProjectStatus
from app.services import project_service as svc
from app.services import upload_service

bp = Blueprint("projects", __name__, url_prefix="/projetos")


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


def _get_project(project_id) -> Project:
    return db.get_or_404(Project, project_id)


def _get_session(project: Project, session_id) -> ProjectSession:
    session = db.get_or_404(ProjectSession, session_id)
    if session.project_id != project.id:
        abort(404)
    return session


def _get_reference(project: Project, reference_id) -> ProjectReference:
    ref = db.get_or_404(ProjectReference, reference_id)
    if ref.project_id != project.id:
        abort(404)
    return ref


# ---------- Projetos ----------
@bp.route("/", strict_slashes=False)
def index():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    projects = svc.search_projects(q, status, page)
    return render_template("projects/list.html", projects=projects, q=q, status=status,
                           statuses=ProjectStatus)


@bp.route("/novo", methods=["GET", "POST"])
def create():
    preselected = request.args.get("cliente", type=int)
    form = ProjectForm()
    if request.method == "GET" and preselected and any(preselected == choice.value for choice in form.client_id.choices):
        form.client_id.data = preselected
    if form.validate_on_submit():
        project = svc.create_project(form.cleaned(), current_user)
        flash("Projeto criado com sucesso.", "success")
        return redirect(url_for("projects.detail", project_id=project.id))
    return render_template("projects/form.html", form=form, project=None), (400 if form.errors else 200)


@bp.route("/<int:project_id>")
def detail(project_id):
    project = _get_project(project_id)
    return render_template("projects/detail.html", project=project,
                           fin=svc.project_financials(project), upload_form=ReferenceUploadForm())


@bp.route("/<int:project_id>/editar", methods=["GET", "POST"])
def edit(project_id):
    project = _get_project(project_id)
    form = ProjectForm(obj=project, current_client_id=project.client_id)
    if request.method == "GET":
        form.status.data = project.status.value
        form.body_region_id.data = project.body_region_id or 0
    if form.validate_on_submit():
        svc.update_project(project, form.cleaned(), current_user)
        flash("Projeto atualizado.", "success")
        return redirect(url_for("projects.detail", project_id=project.id))
    return render_template("projects/form.html", form=form, project=project), (400 if form.errors else 200)


# ---------- Sessões ----------
@bp.route("/<int:project_id>/sessoes/nova", methods=["GET", "POST"])
def session_create(project_id):
    project = _get_project(project_id)
    form = SessionForm()
    if form.validate_on_submit():
        svc.add_session(project, form.cleaned(), current_user)
        flash("Sessão adicionada.", "success")
        return redirect(url_for("projects.detail", project_id=project.id))
    return render_template("projects/session_form.html", form=form, project=project, session=None), (400 if form.errors else 200)


@bp.route("/<int:project_id>/sessoes/<int:session_id>/editar", methods=["GET", "POST"])
def session_edit(project_id, session_id):
    project = _get_project(project_id)
    session = _get_session(project, session_id)
    form = SessionForm(obj=session)
    if request.method == "GET":
        form.status.data = session.status.value
    if form.validate_on_submit():
        svc.update_session(session, form.cleaned(), current_user)
        flash("Sessão atualizada.", "success")
        return redirect(url_for("projects.detail", project_id=project.id))
    return render_template("projects/session_form.html", form=form, project=project, session=session), (400 if form.errors else 200)


@bp.route("/<int:project_id>/sessoes/<int:session_id>/excluir", methods=["POST"])
def session_delete(project_id, session_id):
    project = _get_project(project_id)
    session = _get_session(project, session_id)
    try:
        svc.delete_session(session, current_user)
        flash("Sessão removida.", "info")
    except svc.SessionInUse:
        flash("Esta sessão está vinculada a um atendimento na agenda. Cancele a sessão em vez de excluí-la.", "error")
    return redirect(url_for("projects.detail", project_id=project.id))


# ---------- Imagens de referência ----------
@bp.route("/<int:project_id>/referencias", methods=["POST"])
def reference_upload(project_id):
    project = _get_project(project_id)
    form = ReferenceUploadForm()
    if not form.validate_on_submit():
        flash("Sessão expirada. Recarregue a página e tente novamente.", "error")
        return redirect(url_for("projects.detail", project_id=project.id))
    result = upload_service.save_references(project, form.files.data, current_user)
    if result.saved:
        flash(f"{result.saved} {'imagem adicionada' if result.saved == 1 else 'imagens adicionadas'}.", "success")
    for message in result.errors[:3]:
        flash(message, "error")
    if len(result.errors) > 3:
        flash(f"E mais {len(result.errors) - 3} arquivo(s) recusado(s).", "error")
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.route("/<int:project_id>/referencias/<int:reference_id>")
@bp.route("/<int:project_id>/referencias/<int:reference_id>/miniatura", endpoint="reference_thumb")
def reference_file(project_id, reference_id):
    """Serve a imagem só para usuária autenticada. O caminho vem do banco, nunca da URL."""
    project = _get_project(project_id)
    ref = _get_reference(project, reference_id)
    thumb = request.endpoint.endswith("reference_thumb")
    name = upload_service.thumb_name(ref.stored_filename) if thumb else ref.stored_filename
    response = send_from_directory(upload_service.projects_dir(), name,
                                   mimetype="image/webp" if thumb else upload_service.mimetype_for(name),
                                   max_age=0)
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@bp.route("/<int:project_id>/referencias/<int:reference_id>/excluir", methods=["POST"])
def reference_delete(project_id, reference_id):
    project = _get_project(project_id)
    ref = _get_reference(project, reference_id)
    upload_service.delete_reference(ref, current_user)
    flash("Imagem removida.", "info")
    return redirect(url_for("projects.detail", project_id=project.id))
