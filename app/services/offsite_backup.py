"""Backup cifrado para fora do computador usando Restic (sem guardar credenciais no código)."""
import os
import shutil
import subprocess
from pathlib import Path

from flask import current_app

from app.services.setup_service import backup_database, database_file


class OffsiteBackupError(RuntimeError):
    """Configuração, banco, ferramenta ou destino remoto indisponível."""


def create_offsite_backup() -> str:
    repository = os.environ.get("RESTIC_REPOSITORY", "").strip()
    password_file = os.environ.get("RESTIC_PASSWORD_FILE", "").strip()
    restic = shutil.which("restic")
    if not repository:
        raise OffsiteBackupError("Configure RESTIC_REPOSITORY no ambiente do estúdio.")
    if not password_file or not Path(password_file).expanduser().is_file():
        raise OffsiteBackupError("Configure RESTIC_PASSWORD_FILE apontando para o arquivo de senha do Restic.")
    secret_path = Path(password_file).expanduser().resolve()
    project_dir = Path(current_app.config["ENV_FILE"]).resolve().parent
    if secret_path.is_relative_to(project_dir):
        raise OffsiteBackupError("Guarde o arquivo da senha do Restic fora da pasta do projeto.")
    if secret_path.stat().st_size == 0:
        raise OffsiteBackupError("O arquivo RESTIC_PASSWORD_FILE está vazio.")
    if not restic:
        raise OffsiteBackupError("Restic não encontrado. Instale-o e disponibilize o comando restic no PATH.")
    if repository.startswith("rclone:") and not shutil.which("rclone"):
        raise OffsiteBackupError("rclone não encontrado. Instale-o e disponibilize o comando rclone no PATH.")

    db_path = database_file()
    if db_path is None or not db_path.exists():
        raise OffsiteBackupError("Banco SQLite em arquivo não encontrado; confira DATABASE_URL e rode setup.")
    uploads = Path(current_app.config["UPLOAD_FOLDER"])
    if not uploads.is_dir():
        raise OffsiteBackupError(f"Pasta de uploads não encontrada: {uploads}")

    # Usa a API de snapshot do SQLite para não copiar um banco parcialmente escrito.
    snapshot = backup_database(db_path)
    try:
        completed = subprocess.run(
            [restic, "-r", repository, "--password-file", str(secret_path),
             "backup", "--tag", "agatha-studio", str(snapshot), str(uploads)],
            check=True, capture_output=True, text=True, timeout=60 * 60,
        )
    except subprocess.TimeoutExpired as exc:
        raise OffsiteBackupError("O backup remoto excedeu 60 minutos; confira a conexão e tente novamente.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "sem detalhes").strip()
        raise OffsiteBackupError(f"Restic não concluiu o backup: {detail[-1200:]}") from exc

    return (completed.stdout or "Backup Restic concluído.").strip()
