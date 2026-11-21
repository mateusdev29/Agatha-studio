"""Guia de componentes de interface. Só existe em desenvolvimento/testes."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

bp = Blueprint("dev", __name__)


@bp.route("/_ui", methods=["GET", "POST"])
@login_required
def ui_guide():
    from flask import request
    if request.method == "POST":
        flash("Ação confirmada (demonstração).", "success")
        return redirect(url_for("dev.ui_guide"))
    return render_template("dev/ui.html")
