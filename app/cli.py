"""Comandos de linha de comando: flask seed-base | create-user | seed-dev-user."""
import os
import secrets

import click
from flask import current_app

from app.extensions import db
from app.models import User
from app.services.seed_base import seed_base


def register_cli(app):
    @app.cli.command("reset-password")
    @click.option("--email", prompt="E-mail da conta")
    @click.password_option("--password", prompt="Nova senha", confirmation_prompt=True)
    def reset_password_command(email, password):
        """Redefine a senha de UMA conta existente. Uso explícito: `setup` nunca altera senhas."""
        from app.models.base import utcnow  # noqa: F401  (mantém imports locais do comando)
        from app.services.activity_service import log_activity

        user = User.query.filter_by(email=email.strip().lower()).first()
        if user is None:
            raise click.ClickException("Nenhuma conta com esse e-mail. Nada foi alterado.")
        if len(password) < 10:
            raise click.ClickException("A senha deve ter pelo menos 10 caracteres.")
        user.set_password(password)
        user.failed_login_count, user.locked_until = 0, None            # também destrava a conta
        log_activity("updated", "Senha redefinida pela linha de comando", user, "user", user.id)
        db.session.commit()
        click.echo(f"[OK] Senha de {user.email} redefinida. Nenhum outro dado foi alterado.")

    @app.cli.command("backup")
    def backup_command():
        """Cria uma cópia consistente do banco em instance/backups/ (pode rodar com o sistema aberto)."""
        from app.services.setup_service import backup_database, database_file

        path = database_file()
        if path is None or not path.exists():
            raise click.ClickException("Banco SQLite em arquivo não encontrado. Rode primeiro: flask --app wsgi setup")
        click.echo(f"[OK] Backup criado: {backup_database(path)}")

    @app.cli.command("backup-offsite")
    def backup_offsite_command():
        """Envia uma cópia cifrada do banco e uploads para o repositório Restic configurado."""
        from app.services.offsite_backup import OffsiteBackupError, create_offsite_backup

        try:
            result = create_offsite_backup()
        except OffsiteBackupError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(result)

    @app.cli.command("setup")
    def setup_command():
        """Prepara tudo de forma segura e repetível: .env, banco, migrations, dados-base e administradora."""
        _run_setup()

    @app.cli.command("init")
    def init_command():
        """Atalho para `flask setup`."""
        _run_setup()

    def _dev_admin_values() -> dict:
        """DEV_ADMIN_* do .env (já completado pelo bootstrap), refletindo o que mudou neste processo."""
        from pathlib import Path

        from dotenv import dotenv_values

        import bootstrap

        report = bootstrap.ensure_env(Path(app.config["ENV_FILE"]))
        for key, value in report["updated"].items():
            os.environ[key] = value
        if report["password_created"]:
            click.echo(f"[OK] Senha da administradora gerada e salva no .env: {report['password_created']}")
        values = {**dotenv_values(app.config["ENV_FILE"], encoding="utf-8-sig"),
                  **{k: v for k, v in os.environ.items() if k.startswith("DEV_ADMIN_") and v}}
        return {k: (v or "").strip() for k, v in values.items() if k.startswith("DEV_ADMIN_")}

    def _run_setup():
        from app.services.setup_service import SetupError, run_setup

        try:
            run_setup(_dev_admin_values(), click.echo)
        except SetupError as exc:
            raise click.ClickException(str(exc))
        click.echo("[OK] Sistema pronto.")

    @app.cli.command("set-login")
    def set_login_command():
        """Aplica o login e a senha do .env (DEV_ADMIN_*) à conta de administradora. Só desenvolvimento."""
        from app.services.setup_service import SetupError, apply_login

        if app.config["APP_ENV"] not in ("development", "testing"):
            raise click.ClickException("Comando bloqueado fora do ambiente de desenvolvimento. Em produção use: create-user / reset-password.")
        v = _dev_admin_values()
        try:
            status, user = apply_login(v.get("DEV_ADMIN_EMAIL"), v.get("DEV_ADMIN_NAME"), v.get("DEV_ADMIN_PASSWORD"))
        except SetupError as exc:
            raise click.ClickException(str(exc))
        msg = {"created": "Conta criada", "password_reset": "Senha aplicada à conta existente",
               "identity_updated": "A conta de administradora existente passou a usar este e-mail e esta senha",
               "unchanged": "Nada a alterar: o login do .env já é o da conta"}[status]
        click.echo(f"[OK] {msg}: {user.email}")
        click.echo("     Entre com o e-mail acima e a senha DEV_ADMIN_PASSWORD do arquivo .env.")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """[APENAS DESENVOLVIMENTO] Cria dados FICTÍCIOS de demonstração (marcados com [DEMO])."""
        if current_app.config["APP_ENV"] not in ("development", "testing"):
            raise click.ClickException("Comando bloqueado fora do ambiente de desenvolvimento.")
        from app.seeds.demo import AlreadySeeded, seed_demo
        from app.services.seed_base import seed_base
        seed_base()
        try:
            created = seed_demo()
        except AlreadySeeded as exc:
            raise click.ClickException(str(exc))
        click.echo(f"Dados de DEMONSTRAÇÃO criados: {created}")

    @app.cli.command("seed-base")
    def seed_base_command():
        """Cria regiões corporais, categorias e serviços padrão (idempotente)."""
        created = seed_base()
        click.echo(f"Dados-base OK: {created}")

    @app.cli.command("create-user")
    @click.option("--name", prompt="Nome")
    @click.option("--email", prompt="E-mail")
    @click.password_option("--password", prompt="Senha", confirmation_prompt=True)
    def create_user_command(name, email, password):
        """Cria um usuário administrador (uso em produção)."""
        email = email.strip().lower()
        if len(password) < 10:
            raise click.ClickException("A senha deve ter pelo menos 10 caracteres.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("Já existe um usuário com esse e-mail.")
        user = User(name=name.strip(), email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Usuário criado: {email}")

    @app.cli.command("seed-dev-user")
    def seed_dev_user_command():
        """[APENAS DESENVOLVIMENTO] Cria o usuário inicial a partir do .env."""
        if current_app.config["APP_ENV"] not in ("development", "testing"):
            raise click.ClickException("Comando bloqueado fora do ambiente de desenvolvimento.")

        email = os.environ.get("DEV_ADMIN_EMAIL", "agatha@example.com").strip().lower()
        name = os.environ.get("DEV_ADMIN_NAME", "Agatha Souza")
        password = os.environ.get("DEV_ADMIN_PASSWORD")
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12)

        user = User.query.filter_by(email=email).first()
        if user:
            raise click.ClickException(f"Usuário {email} já existe. Nada foi alterado.")

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Usuário de desenvolvimento criado: {email}")
        if generated:
            click.echo(f"Senha gerada (exibida uma única vez): {password}")
