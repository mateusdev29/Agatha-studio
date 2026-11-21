"""Preparação inicial segura e idempotente: banco, migrations, dados-base e administrador.

Garantias (todas testadas):
- nunca apaga, recria ou sobrescreve dados ou usuários existentes;
- só executa migrations pendentes e, se o banco já tiver dados, faz um backup antes;
- nunca troca a senha de um usuário existente e nunca gera senha aleatória aqui
  (a senha vem do .env; quem a gera, uma única vez, é o bootstrap.py);
- rodar várias vezes dá sempre o mesmo resultado.
"""
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from email_validator import EmailNotValidError, validate_email
from flask import current_app
from flask_migrate import upgrade
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from app.extensions import db
from app.models import User
from app.services.activity_service import log_activity
from app.services.seed_base import seed_base

MIN_PASSWORD = 10
KEEP_BACKUPS = 5


class SetupError(Exception):
    """Problema que exige ação da usuária; a mensagem diz o que fazer."""


def database_file() -> Path | None:
    """Caminho do arquivo SQLite (None para banco em memória ou não-SQLite)."""
    url = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def schema_state() -> tuple[str, str | None, str | None]:
    """('new'|'ok'|'pending'|'unversioned', revisão atual, revisão mais recente)."""
    head = ScriptDirectory(current_app.config["MIGRATIONS_DIR"]).get_current_head()
    with db.engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        current = MigrationContext.configure(conn).get_current_revision() if "alembic_version" in tables else None
    if not tables:
        return "new", None, head
    if current is None:
        return "unversioned", None, head       # há tabelas, mas sem controle de migrations
    return ("ok" if current == head else "pending"), current, head


def backup_database(path: Path, keep: int = KEEP_BACKUPS) -> Path:
    """Cópia consistente (API de backup do SQLite) em instance/backups/. Mantém só as `keep` mais recentes."""
    folder = path.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(path), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(folder.glob(f"{path.stem}-*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    return target


def _has_data(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _validated(email: str, name: str, password: str) -> tuple[str, str]:
    """Valida o login vindo do .env. Retorna (e-mail normalizado, nome)."""
    email = (email or "").strip().lower()
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise SetupError(f"DEV_ADMIN_EMAIL inválido no .env: {email!r}.")
    if len(password or "") < MIN_PASSWORD:
        raise SetupError(f"DEV_ADMIN_PASSWORD no .env precisa ter pelo menos {MIN_PASSWORD} caracteres "
                         "(ou deixe em branco e rode `python bootstrap.py` para gerar uma).")
    return email, (name or "").strip() or "Administradora"


def apply_login(email: str, name: str, password: str) -> tuple[str, User]:
    """Aplica o login do .env. Só roda quando a usuária pede (`flask set-login` / `start.bat login`).

    ('created'|'password_reset'|'identity_updated'|'unchanged', usuário). Não apaga dados: só ajusta credenciais.
    Idempotente: se a senha já confere, não regrava o hash.
    """
    email, name = _validated(email, name, password)
    user = User.query.filter_by(email=email).first()
    status = "unchanged"
    if user is None:
        admin = User.query.filter_by(role="admin").order_by(User.id).first()
        if admin:                                   # sistema de uma só profissional: a conta existente passa a ser este login
            admin.email, admin.name, user, status = email, name, admin, "identity_updated"
        else:
            user, status = User(name=name, email=email, role="admin"), "created"
            db.session.add(user)
    password_differs = not user.password_hash or not user.check_password(password)
    needs_unlock = user.role != "admin" or not user.is_active_flag or bool(user.failed_login_count) or user.locked_until is not None
    if password_differs:
        user.set_password(password)
    if needs_unlock:
        user.role, user.is_active_flag, user.failed_login_count, user.locked_until = "admin", True, 0, None
    if status == "unchanged" and (password_differs or needs_unlock):
        status = "password_reset"
    if status != "unchanged":
        db.session.flush()
        log_activity("updated", "Login da administradora aplicado a partir do .env", user, "user", user.id)
    db.session.commit()
    return status, user


def ensure_admin(email: str, name: str, password: str) -> tuple[str, User]:
    """('exists'|'created', usuário). Nunca altera um usuário existente."""
    admin = User.query.filter_by(role="admin", is_active_flag=True).order_by(User.id).first()
    if admin:
        return "exists", admin

    email, name = _validated(email, name, password)
    if User.query.filter_by(email=email).first():
        raise SetupError(f"Já existe um usuário {email} que não é um administrador ativo. Nada foi alterado: "
                         "use outro e-mail no .env ou ajuste esse usuário.")
    user = User(name=name, email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return "created", user


def run_setup(env: dict, echo) -> dict:
    """Executa a preparação. `env` = variáveis (DEV_ADMIN_*); `echo` = função de saída."""
    result = {"migrated": False, "backup": None, "admin": None, "admin_email": None, "created_db": False}
    Path(current_app.instance_path).mkdir(parents=True, exist_ok=True)
    path = database_file()

    state, current, head = schema_state()
    if state == "unversioned":
        raise SetupError("O banco já tem tabelas, mas não tem controle de migrations (provavelmente foi criado de outra "
                         "forma). Por segurança nada foi alterado. Faça uma cópia do arquivo do banco, depois renomeie-o "
                         "para o sistema criar um novo, ou peça ajuda para registrar a versão do schema.")

    if state == "new":
        echo("[OK] Banco novo: criando tabelas...")
        result["created_db"] = True
    elif state == "pending":
        if path and _has_data(path):
            result["backup"] = backup_database(path)
            echo(f"[OK] Backup do banco antes de atualizar: {result['backup']}")
        echo(f"[OK] Atualizando banco ({current} -> {head})...")
    else:
        echo("[OK] Banco existente e atualizado (nada a migrar).")

    if state in ("new", "pending"):
        upgrade(directory=current_app.config["MIGRATIONS_DIR"])
        result["migrated"] = True

    created = seed_base()
    added = sum(created.values())
    echo(f"[OK] Dados-base {'criados' if added else 'já presentes'}" + (f" ({added} novos)." if added else "."))

    if current_app.config["APP_ENV"] in ("development", "testing"):
        status, user = ensure_admin(env.get("DEV_ADMIN_EMAIL"), env.get("DEV_ADMIN_NAME"), env.get("DEV_ADMIN_PASSWORD"))
        result["admin"], result["admin_email"] = status, user.email
        if status == "created":
            echo(f"[OK] Administradora criada: {user.email}")
        else:
            echo(f"[OK] Administradora já existe ({user.email}); nenhuma conta foi alterada.")
    elif not User.query.filter_by(role="admin", is_active_flag=True).first():
        echo("[AVISO] Nenhuma administradora cadastrada. Em produção crie com: flask --app wsgi create-user")
    return result
