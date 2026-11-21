"""Páginas de erro amigáveis, sem expor detalhes internos."""
from flask import Blueprint, render_template
from flask_wtf.csrf import CSRFError

from app.extensions import db

bp = Blueprint("errors", __name__)

MESSAGES = {
    400: ("Requisição inválida", "Não foi possível processar a solicitação."),
    403: ("Acesso negado", "Você não tem permissão para acessar esta página."),
    404: ("Página não encontrada", "O endereço solicitado não existe."),
    413: ("Arquivo muito grande", "O arquivo enviado excede o tamanho permitido."),
    500: ("Algo deu errado", "Ocorreu um erro inesperado. Tente novamente."),
}


def _render(code):
    title, message = MESSAGES.get(code, MESSAGES[500])
    return render_template("errors/error.html", code=code, title=title, message=message), code


@bp.app_errorhandler(CSRFError)
def csrf_error(_e):
    return render_template(
        "errors/error.html", code=400, title="Sessão expirada",
        message="Recarregue a página e tente novamente.",
    ), 400


@bp.app_errorhandler(400)
def bad_request(_e):
    return _render(400)


@bp.app_errorhandler(403)
def forbidden(_e):
    return _render(403)


@bp.app_errorhandler(404)
def not_found(_e):
    return _render(404)


@bp.app_errorhandler(413)
def too_large(_e):
    return _render(413)


@bp.app_errorhandler(500)
def server_error(_e):
    db.session.rollback()
    return _render(500)
