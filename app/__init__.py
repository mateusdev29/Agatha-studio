"""Application factory do AGATHA SOUZA STUDIO — Gestão do Estúdio."""
import logging
import os
import secrets
from pathlib import Path

from flask import Flask

from config import BASE_DIR, CONFIGS
from app.extensions import csrf, db, login_manager, migrate
from app.utils.formatting import register_filters

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("APP_ENV", "development")
    if config_name not in CONFIGS:
        raise RuntimeError(f"APP_ENV inválido: {config_name!r}")

    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.from_object(CONFIGS[config_name])
    app.config["APP_ENV"] = config_name
    Path(app.instance_path).mkdir(exist_ok=True)

    _ensure_secret_key(app)

    db.init_app(app)
    _harden_sqlite(app)
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIR"])   # funciona de qualquer pasta
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registra todos os modelos)
    from app.cli import register_cli
    from app.routes import agenda, anamnesis, auth, clients, errors, finance, insights, main, projects, quotes, settings, stock

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(quotes.bp)
    app.register_blueprint(agenda.bp)
    app.register_blueprint(finance.bp)
    app.register_blueprint(stock.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(anamnesis.bp)
    for bp in (insights.dashboard_bp, insights.satisfaction_bp, insights.body_bp):
        app.register_blueprint(bp)
    app.register_blueprint(errors.bp)
    register_cli(app)

    if config_name in ("development", "testing"):
        from app.routes import dev
        app.register_blueprint(dev.bp)

    register_filters(app)
    from app.utils.periods import PRESETS
    app.jinja_env.globals["presets"] = PRESETS
    register_context(app)
    register_hooks(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    return app


_SQLITE_HARDENED = False


def _harden_sqlite(app: Flask) -> None:
    """SQLite não impõe chaves estrangeiras por padrão; liga FK. Registrado uma única vez (listener global).
    O modo WAL NÃO é usado de propósito: ele espalha dados em arquivos -wal/-shm e copiar só o .db perderia
    dados. Sem WAL o banco é um único arquivo, seguro de copiar com o servidor parado."""
    global _SQLITE_HARDENED
    if _SQLITE_HARDENED:
        return
    _SQLITE_HARDENED = True
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def _pragmas(dbapi_conn, _record):
        if not dbapi_conn.__class__.__module__.startswith("sqlite3"):
            return
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def register_hooks(app: Flask) -> None:
    """Expira orçamentos vencidos (no máximo 1x por hora por processo, só com usuária logada)."""
    from flask import request
    from flask_login import current_user
    from sqlalchemy.exc import SQLAlchemyError

    @app.before_request
    def expire_quotes():
        if request.endpoint in (None, "static") or not current_user.is_authenticated:
            return
        from app.services.quote_service import expire_overdue
        try:
            expire_overdue()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Falha ao expirar orçamentos")


def register_context(app: Flask) -> None:
    """Dados globais da casca: menu lateral e avisos do sino."""
    from flask import request
    from flask_login import current_user
    from sqlalchemy.exc import SQLAlchemyError

    from app.navigation import NAV_GROUPS, is_active
    from app.services.notification_service import get_notifications

    @app.context_processor
    def shell_context():
        if not current_user.is_authenticated:
            return {}
        groups = [[{"label": i.label, "icon": i.icon, "path": i.path, "active": is_active(i, request.path)}
                   for i in group] for group in NAV_GROUPS]
        try:
            notifications = get_notifications()
        except SQLAlchemyError:  # o aviso nunca pode derrubar a página (nem a de erro)
            db.session.rollback()
            app.logger.exception("Falha ao calcular notificações")
            notifications = []
        return {"nav_groups": groups, "notifications": notifications}


def _ensure_secret_key(app: Flask) -> None:
    """SECRET_KEY estável. Produção exige a variável; desenvolvimento nunca usa chave que mude a cada início."""
    if app.config.get("SECRET_KEY"):
        return
    if app.config.get("REQUIRE_SECRET_KEY"):
        raise RuntimeError("SECRET_KEY não definida. Defina no .env (veja o README: gere com "
                           "python -c \"import secrets; print(secrets.token_hex(32))\").")
    # Desenvolvimento sem SECRET_KEY no .env: guarda uma chave local persistente (instance/dev_secret_key),
    # para reinícios, o reloader do --debug e vários processos usarem a MESMA chave e as sessões sobrevivam.
    path = Path(app.instance_path) / "dev_secret_key"
    key = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if len(key) < 32:
        key = secrets.token_hex(32)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(key, encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass                                          # Windows: chmod é limitado; a pasta já é privada
        key = path.read_text(encoding="utf-8").strip()    # se outro processo gravou primeiro, usa a dele
    app.config["SECRET_KEY"] = key
    logging.getLogger(__name__).warning(
        "SECRET_KEY ausente no .env: usando a chave local persistente em instance/dev_secret_key. "
        "Rode `python bootstrap.py` (ou start.bat) para gravar uma no .env.")
