from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required

from app.forms.auth import LoginForm
from app.services import auth_service
from app.utils.security import is_safe_redirect_url

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()
    if form.validate_on_submit():
        result = auth_service.authenticate(
            form.email.data, form.password.data,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )
        if result.ok:
            login_user(result.user, remember=form.remember.data)
            next_url = request.args.get("next")
            return redirect(next_url if is_safe_redirect_url(next_url) else url_for("main.home"))
        flash(result.error, "error")

    return render_template("auth/login.html", form=form), (400 if form.errors else 200)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("auth.login"))
