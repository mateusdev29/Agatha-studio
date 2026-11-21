from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.appointments import AppointmentForm, DepositForm, RescheduleForm
from app.models import Appointment, Service
from app.models.enums import AppointmentStatus
from app.services import appointment_service as svc
from app.services import calendar_service as cal
from app.services import deposit_service as dep
from app.models.enums import PaymentMethod, TransactionStatus
from app.services.settings_service import default_duration
from app.utils.dates import now_local, today_local

bp = Blueprint("agenda", __name__, url_prefix="/agenda")


@bp.before_request
@login_required
def _require_login():
    """Todas as rotas deste módulo exigem autenticação."""


def _get(appt_id) -> Appointment:
    return db.get_or_404(Appointment, appt_id)


def _detail(appt):
    return redirect(url_for("agenda.detail", appt_id=appt.id))


def _services():
    return Service.query.filter_by(is_active=True).order_by(Service.name).all()


@bp.route("/", strict_slashes=False)
def index():
    view = cal.parse_view(request.args.get("vista"))
    anchor = cal.parse_date(request.args.get("data"))
    return render_template("agenda/index.html", cal=cal.build_calendar(view, anchor), view=view,
                           anchor=anchor, today=today_local(), weekdays=cal.WEEKDAY_HEADERS)


@bp.route("/novo", methods=["GET", "POST"])
def create():
    form = AppointmentForm()
    if request.method == "GET":
        client_id = request.args.get("cliente", type=int)
        if client_id and any(client_id == c for c, _ in form.client_id.choices):
            form.client_id.data = client_id
        project_id = request.args.get("projeto", type=int)
        if project_id and any(project_id == p[0] for p in form.project_id.choices):
            form.project_id.data = project_id
        form.date.data = cal.parse_date(request.args.get("data"))
        form.duration_minutes.data = default_duration()
    if form.validate_on_submit():
        try:
            appt = svc.create_appointment(form.cleaned(), current_user)
        except svc.AppointmentError as exc:
            form.time.errors = list(form.time.errors) + [str(exc)]
        else:
            flash("Atendimento agendado.", "success")
            return _detail(appt)
    return render_template("agenda/form.html", form=form, appt=None, services=_services(), deposit_locked=False), (400 if form.errors else 200)


@bp.route("/<int:appt_id>")
def detail(appt_id):
    appt = _get(appt_id)
    deposit_form = DepositForm()
    deposit_form.date.data = today_local()
    return render_template("agenda/detail.html", appt=appt, S=AppointmentStatus, editable=svc.is_editable(appt),
                           can_mark_done=appt.starts_at <= now_local(),
                           deposit=dep.deposit_transaction(appt), deposit_form=deposit_form)


@bp.route("/<int:appt_id>/editar", methods=["GET", "POST"])
def edit(appt_id):
    appt = _get(appt_id)
    if not svc.is_editable(appt):
        flash("Só atendimentos aguardando ou confirmados podem ser editados.", "error")
        return _detail(appt)
    form = AppointmentForm(obj=appt, current_client_id=appt.client_id, current_project_id=appt.project_id)
    if request.method == "GET":
        form.date.data, form.time.data = appt.starts_at.date(), appt.starts_at.time()
        form.project_id.data = appt.project_id or 0
    if form.validate_on_submit():
        try:
            svc.update_appointment(appt, form.cleaned(), current_user)
        except svc.AppointmentError as exc:
            form.time.errors = list(form.time.errors) + [str(exc)]
        else:
            flash("Atendimento atualizado.", "success")
            return _detail(appt)
    return render_template("agenda/form.html", form=form, appt=appt, services=_services(),
                           deposit_locked=dep.deposit_transaction(appt) is not None), (400 if form.errors else 200)


@bp.route("/<int:appt_id>/sinal", methods=["POST"])
def launch_deposit(appt_id):
    appt = _get(appt_id)
    form = DepositForm()
    if form.validate_on_submit():
        try:
            dep.launch_deposit(appt, PaymentMethod(form.payment_method.data) if form.payment_method.data else None,
                               form.date.data, TransactionStatus(form.status.data), current_user)
            flash("Sinal lançado no Financeiro.", "success")
        except dep.DepositError as exc:
            flash(str(exc), "error")
    else:
        flash(next((e for errs in form.errors.values() for e in errs), "Dados inválidos."), "error")
    return _detail(appt)


def _transition(appt_id, target, success):
    appt = _get(appt_id)
    try:
        svc.change_status(appt, target, current_user)
        flash(success, "success")
    except svc.AppointmentError as exc:
        flash(str(exc), "error")
    return _detail(appt)


@bp.route("/<int:appt_id>/confirmar", methods=["POST"])
def confirm(appt_id):
    return _transition(appt_id, AppointmentStatus.CONFIRMED, "Atendimento confirmado.")


@bp.route("/<int:appt_id>/realizar", methods=["POST"])
def finish(appt_id):
    return _transition(appt_id, AppointmentStatus.DONE, "Atendimento marcado como realizado.")


@bp.route("/<int:appt_id>/cancelar", methods=["POST"])
def cancel(appt_id):
    return _transition(appt_id, AppointmentStatus.CANCELED, "Atendimento cancelado.")


@bp.route("/<int:appt_id>/reativar", methods=["POST"])
def reactivate(appt_id):
    return _transition(appt_id, AppointmentStatus.WAITING, "Atendimento reativado.")


@bp.route("/<int:appt_id>/remarcar", methods=["GET", "POST"])
def reschedule(appt_id):
    appt = _get(appt_id)
    if not svc.is_editable(appt):
        flash("Só atendimentos aguardando ou confirmados podem ser remarcados.", "error")
        return _detail(appt)
    form = RescheduleForm()
    if request.method == "GET":
        form.date.data, form.time.data, form.duration_minutes.data = appt.starts_at.date(), appt.starts_at.time(), appt.duration_minutes
    if form.validate_on_submit():
        try:
            new = svc.reschedule(appt, form.starts_at, form.duration_minutes.data, current_user)
        except svc.AppointmentError as exc:
            form.time.errors = list(form.time.errors) + [str(exc)]
        else:
            flash("Atendimento remarcado. Aguardando nova confirmação.", "success")
            return _detail(new)
    return render_template("agenda/reschedule.html", form=form, appt=appt), (400 if form.errors else 200)
