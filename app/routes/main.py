from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services.overview_service import get_overview

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def home():
    return render_template("main/home.html", user=current_user, overview=get_overview())
