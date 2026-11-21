"""Upload seguro de imagens de referência.

Princípios:
- Nunca confiar no nome, extensão ou Content-Type enviados: o arquivo é aberto e validado
  pelo Pillow, e o formato real decide a extensão.
- O nome gravado é gerado pelo servidor (uuid); o nome original só é guardado para exibição.
- A imagem é re-codificada: remove EXIF/GPS e qualquer carga anexada ao arquivo.
- Arquivos ficam fora de /static e só são servidos por rota autenticada.
"""
import io
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Project, ProjectReference
from app.services.activity_service import log_activity

FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


@dataclass
class UploadResult:
    saved: int = 0
    errors: list[str] = field(default_factory=list)


def projects_dir() -> Path:
    path = Path(current_app.config["UPLOAD_FOLDER"]) / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def thumb_name(stored_filename: str) -> str:
    return stored_filename.rsplit(".", 1)[0] + "_thumb.webp"


def mimetype_for(stored_filename: str) -> str:
    ext = stored_filename.rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "application/octet-stream")


def _display_name(raw: str | None) -> str:
    name = secure_filename(Path((raw or "").replace("\\", "/")).name)
    return (name or "imagem")[:150]


class InvalidImage(Exception):
    pass


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    elif fmt == "PNG":
        img.save(buf, "PNG", optimize=True)
    else:
        img.save(buf, "WEBP", quality=90)
    return buf.getvalue()


def process_image(data: bytes, filename: str) -> tuple[str, bytes, bytes]:
    """Valida e normaliza. Retorna (formato, bytes_da_imagem, bytes_da_miniatura)."""
    cfg = current_app.config
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in cfg["ALLOWED_IMAGE_EXTENSIONS"]:
        raise InvalidImage("formato não permitido (use JPG, PNG ou WEBP)")
    if len(data) > cfg["MAX_UPLOAD_FILE_BYTES"]:
        raise InvalidImage(f"maior que {cfg['MAX_UPLOAD_FILE_BYTES'] // (1024 * 1024)} MB")

    try:
        img = Image.open(io.BytesIO(data))        # lê só o cabeçalho
        fmt = img.format
        if fmt not in FORMATS:
            raise InvalidImage("o conteúdo não é uma imagem JPG, PNG ou WEBP")
        if img.width * img.height > cfg["MAX_IMAGE_PIXELS"]:
            raise InvalidImage("dimensões grandes demais")
        img = ImageOps.exif_transpose(img)         # respeita a rotação da foto antes de remover o EXIF
        img.load()                                 # decodifica de fato: arquivos corrompidos falham aqui
    except InvalidImage:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        raise InvalidImage("arquivo corrompido ou não é uma imagem")

    side = cfg["IMAGE_MAX_SIDE"]
    full = img.copy()
    full.thumbnail((side, side))
    thumb = img.copy()
    thumb.thumbnail((cfg["THUMBNAIL_SIDE"],) * 2)
    thumb_buf = io.BytesIO()
    thumb.convert("RGBA" if "A" in thumb.getbands() else "RGB").save(thumb_buf, "WEBP", quality=80)
    return fmt, _encode(full, fmt), thumb_buf.getvalue()


def save_references(project: Project, files, user) -> UploadResult:
    """Salva as imagens válidas e reporta as recusadas (uma recusa não cancela as demais)."""
    result = UploadResult()
    cfg = current_app.config
    files = [f for f in (files or []) if f and f.filename]
    if not files:
        result.errors.append("Selecione ao menos uma imagem.")
        return result

    room = cfg["MAX_REFERENCES_PER_PROJECT"] - len(project.references)
    written: list[Path] = []
    try:
        for storage in files:
            name = _display_name(storage.filename)
            if room <= 0:
                result.errors.append(f"{name}: limite de {cfg['MAX_REFERENCES_PER_PROJECT']} imagens por projeto atingido.")
                continue
            try:
                data = storage.read(cfg["MAX_UPLOAD_FILE_BYTES"] + 1)
                fmt, full_bytes, thumb_bytes = process_image(data, storage.filename)
            except InvalidImage as exc:
                result.errors.append(f"{name}: {exc}.")
                continue

            stored = f"{uuid.uuid4().hex}.{FORMATS[fmt][0]}"
            directory = projects_dir()
            (directory / stored).write_bytes(full_bytes)
            written.append(directory / stored)
            (directory / thumb_name(stored)).write_bytes(thumb_bytes)
            written.append(directory / thumb_name(stored))
            db.session.add(ProjectReference(project_id=project.id, stored_filename=stored, original_filename=name))
            room -= 1
            result.saved += 1

        if result.saved:
            log_activity("updated", f"{result.saved} imagem(ns) de referência no projeto {project.name}",
                         user, "project", project.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        for path in written:                       # não deixa arquivos órfãos se o banco falhar
            path.unlink(missing_ok=True)
        raise
    return result


def delete_reference(reference: ProjectReference, user) -> None:
    directory = projects_dir()
    stored = reference.stored_filename
    log_activity("deleted", f"Imagem de referência removida do projeto {reference.project.name}",
                 user, "project", reference.project_id)
    db.session.delete(reference)
    db.session.commit()
    (directory / stored).unlink(missing_ok=True)   # só apaga o arquivo depois que o banco confirmou
    (directory / thumb_name(stored)).unlink(missing_ok=True)
