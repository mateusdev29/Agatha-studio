import io
import re
from pathlib import Path

import pytest
from PIL import Image

from app.extensions import db
from app.models import ActivityLog, Client, Project, ProjectReference
from app.services import upload_service
from tests.helpers import image_bytes, jpeg_with_exif, upload


@pytest.fixture()
def project(app):
    c = Client(name="Marina"); db.session.add(c); db.session.flush()
    p = Project(client_id=c.id, name="Floral"); db.session.add(p); db.session.commit()
    return p


def post_files(client, project, *files, field="files"):
    return client.post(f"/projetos/{project.id}/referencias", data={field: list(files)},
                       content_type="multipart/form-data")


def stored_files(app):
    d = Path(app.config["UPLOAD_FOLDER"]) / "projects"
    return sorted(p for p in d.glob("*")) if d.exists() else []


# ---------- Casos válidos ----------
@pytest.mark.parametrize("fmt,ext,mime", [("PNG", "png", "image/png"), ("JPEG", "jpg", "image/jpeg"), ("WEBP", "webp", "image/webp")])
def test_valid_formats_are_saved(app, auth_client, project, fmt, ext, mime):
    r = post_files(auth_client, project, upload(f"foto.{ext}", image_bytes(fmt)))
    assert r.status_code == 302
    ref = ProjectReference.query.one()
    assert re.fullmatch(rf"[0-9a-f]{{32}}\.{ext}", ref.stored_filename)        # nome gerado pelo servidor
    assert len(stored_files(app)) == 2                                          # imagem + miniatura
    assert Image.open(stored_files(app)[0]).format in ("JPEG", "PNG", "WEBP")
    assert ActivityLog.query.filter_by(entity_type="project", entity_id=project.id, action="updated").count() == 1


def test_jpeg_extension_variants_accepted(app, auth_client, project):
    post_files(auth_client, project, upload("FOTO.JPEG", image_bytes("JPEG")))
    assert ProjectReference.query.one().stored_filename.endswith(".jpg")        # extensão vem do formato real


def test_multiple_files_in_one_request(app, auth_client, project):
    post_files(auth_client, project, upload("a.png", image_bytes("PNG")), upload("b.jpg", image_bytes("JPEG")))
    assert ProjectReference.query.count() == 2 and len(stored_files(app)) == 4


def test_large_image_is_downscaled(app, auth_client, project):
    app.config["IMAGE_MAX_SIDE"] = 100
    post_files(auth_client, project, upload("big.png", image_bytes("PNG", size=(400, 200))))
    ref = ProjectReference.query.one()
    img = Image.open(Path(app.config["UPLOAD_FOLDER"]) / "projects" / ref.stored_filename)
    assert max(img.size) == 100 and img.size == (100, 50)


# ---------- Privacidade ----------
def test_exif_and_gps_are_stripped(app, auth_client, project):
    original = jpeg_with_exif()
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)          # a foto de entrada TEM GPS
    post_files(auth_client, project, upload("gps.jpg", original, "image/jpeg"))
    ref = ProjectReference.query.one()
    saved = Image.open(Path(app.config["UPLOAD_FOLDER"]) / "projects" / ref.stored_filename)
    assert len(saved.getexif()) == 0
    raw = (Path(app.config["UPLOAD_FOLDER"]) / "projects" / ref.stored_filename).read_bytes()
    assert b"CameraMaker" not in raw


def test_exif_orientation_is_applied_before_stripping(app, auth_client, project):
    post_files(auth_client, project, upload("rot.jpg", jpeg_with_exif(size=(40, 20), orientation=6), "image/jpeg"))
    ref = ProjectReference.query.one()
    img = Image.open(Path(app.config["UPLOAD_FOLDER"]) / "projects" / ref.stored_filename)
    assert img.size == (20, 40)                                                  # girada, como a foto aparecia


# ---------- Arquivos maliciosos ou inválidos ----------
@pytest.mark.parametrize("name,data", [
    ("script.png", b"<script>alert(1)</script>"),
    ("pagina.jpg", b"<html><body>oi</body></html>"),
    ("shell.php.png", b"<?php system($_GET['c']); ?>"),
    ("vazio.png", b""),
    ("gif_disfarcado.png", image_bytes("GIF")),
    ("bmp_disfarcado.jpg", image_bytes("BMP")),
    ("truncada.png", image_bytes("PNG", size=(200, 200))[:60]),
])
def test_disguised_or_corrupt_files_are_rejected(app, auth_client, project, name, data):
    r = post_files(auth_client, project, upload(name, data), upload("ok.png", image_bytes("PNG")))
    assert r.status_code == 302
    assert ProjectReference.query.count() == 1                                    # só a boa
    assert len(stored_files(app)) == 2


@pytest.mark.parametrize("name", ["foto.gif", "arte.svg", "doc.pdf", "run.exe", "sem_extensao", "foto.png.php"])
def test_disallowed_extensions_are_rejected(app, auth_client, project, name):
    post_files(auth_client, project, upload(name, image_bytes("PNG")))
    assert ProjectReference.query.count() == 0 and stored_files(app) == []


def test_png_with_appended_payload_is_sanitized(app, auth_client, project):
    payload = b"<?php system('id'); ?>MARCADOR-MALICIOSO"
    post_files(auth_client, project, upload("poliglota.png", image_bytes("PNG") + payload))
    for f in stored_files(app):
        assert b"MARCADOR-MALICIOSO" not in f.read_bytes() and b"<?php" not in f.read_bytes()


def test_filename_cannot_escape_upload_dir(app, auth_client, project, tmp_path):
    post_files(auth_client, project, upload("../../../evil.png", image_bytes("PNG")),
               upload("..\\..\\win.png", image_bytes("PNG")))
    for ref in ProjectReference.query.all():
        assert "/" not in ref.stored_filename and ".." not in ref.stored_filename
        assert "/" not in ref.original_filename and "\\" not in ref.original_filename and ".." not in ref.original_filename
    assert not (tmp_path / "evil.png").exists()
    assert all(f.parent == Path(app.config["UPLOAD_FOLDER"]) / "projects" for f in stored_files(app))


def test_original_filename_is_escaped_in_page(app, auth_client, project):
    post_files(auth_client, project, upload('"><script>alert(1)</script>.png', image_bytes("PNG")))
    html = auth_client.get(f"/projetos/{project.id}").get_data(as_text=True)
    assert "<script>alert(1)" not in html


# ---------- Limites ----------
def test_file_size_limit(app, auth_client, project):
    app.config["MAX_UPLOAD_FILE_BYTES"] = 500
    r = post_files(auth_client, project, upload("grande.png", image_bytes("PNG", size=(300, 300))))
    assert r.status_code == 302 and ProjectReference.query.count() == 0


def test_pixel_limit_blocks_decompression_bombs(app, auth_client, project):
    app.config["MAX_IMAGE_PIXELS"] = 100
    post_files(auth_client, project, upload("pixels.png", image_bytes("PNG", size=(50, 50))))
    assert ProjectReference.query.count() == 0


def test_per_project_reference_limit(app, auth_client, project):
    app.config["MAX_REFERENCES_PER_PROJECT"] = 2
    post_files(auth_client, project, *[upload(f"{i}.png", image_bytes("PNG")) for i in range(3)])
    assert ProjectReference.query.count() == 2
    r = auth_client.get(f"/projetos/{project.id}")
    assert "2 de 2" in r.get_data(as_text=True)


def test_request_size_limit_returns_413(app, auth_client, project):
    app.config["MAX_CONTENT_LENGTH"] = 1000
    r = post_files(auth_client, project, upload("a.png", image_bytes("PNG", size=(300, 300))))
    assert r.status_code == 413 and ProjectReference.query.count() == 0


def test_empty_submission_shows_message(app, auth_client, project):
    r = auth_client.post(f"/projetos/{project.id}/referencias", data={}, follow_redirects=True)
    assert "Selecione ao menos uma imagem." in r.get_data(as_text=True)


def test_upload_requires_csrf_token(app, auth_client, project):
    app.config["WTF_CSRF_ENABLED"] = True
    assert post_files(auth_client, project, upload("a.png", image_bytes("PNG"))).status_code == 400
    assert ProjectReference.query.count() == 0


def test_no_orphan_files_if_database_fails(app, project, monkeypatch):
    from werkzeug.datastructures import FileStorage

    def boom():
        raise RuntimeError("banco indisponível")
    monkeypatch.setattr(upload_service.db.session, "commit", boom)
    with pytest.raises(RuntimeError):
        upload_service.save_references(project, [FileStorage(io.BytesIO(image_bytes("PNG")), "a.png")], None)
    assert stored_files(app) == []


# ---------- Servir arquivos ----------
def _saved_ref(app, client, project, fmt="PNG", name="a.png"):
    post_files(client, project, upload(name, image_bytes(fmt)))
    return ProjectReference.query.order_by(ProjectReference.id.desc()).first()


def test_files_are_served_only_to_logged_in_users(app, auth_client, project, client):
    ref = _saved_ref(app, auth_client, project)
    url = f"/projetos/{project.id}/referencias/{ref.id}"
    assert auth_client.get(url).status_code == 200
    # Contexto novo: o `g` do Flask-Login vazaria o usuário logado entre requisições do mesmo teste.
    with app.app_context():
        anon = app.test_client()
        for u in (url, url + "/miniatura"):
            r = anon.get(u)
            assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_served_file_headers(app, auth_client, project):
    ref = _saved_ref(app, auth_client, project)
    full = auth_client.get(f"/projetos/{project.id}/referencias/{ref.id}")
    assert full.mimetype == "image/png" and full.headers["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in full.headers["Content-Security-Policy"] and "private" in full.headers["Cache-Control"]
    assert Image.open(io.BytesIO(full.data)).format == "PNG"
    thumb = auth_client.get(f"/projetos/{project.id}/referencias/{ref.id}/miniatura")
    assert thumb.mimetype == "image/webp" and Image.open(io.BytesIO(thumb.data)).format == "WEBP"


def test_cannot_read_reference_through_another_project(app, auth_client, project):
    ref = _saved_ref(app, auth_client, project)
    other = Project(client_id=project.client_id, name="Outro"); db.session.add(other); db.session.commit()
    assert auth_client.get(f"/projetos/{other.id}/referencias/{ref.id}").status_code == 404
    assert auth_client.post(f"/projetos/{other.id}/referencias/{ref.id}/excluir").status_code == 404
    assert ProjectReference.query.count() == 1


def test_missing_file_and_unknown_ids_are_404(app, auth_client, project):
    ref = _saved_ref(app, auth_client, project)
    for f in stored_files(app):
        f.unlink()
    assert auth_client.get(f"/projetos/{project.id}/referencias/{ref.id}").status_code == 404
    assert auth_client.get(f"/projetos/{project.id}/referencias/9999").status_code == 404
    assert auth_client.get(f"/projetos/{project.id}/referencias/abc").status_code == 404
    assert auth_client.get(f"/projetos/{project.id}/referencias/..%2f..%2fconfig.py").status_code == 404


def test_gallery_renders_thumbnail_and_full_links(app, auth_client, project):
    ref = _saved_ref(app, auth_client, project)
    html = auth_client.get(f"/projetos/{project.id}").get_data(as_text=True)
    assert f"/projetos/{project.id}/referencias/{ref.id}/miniatura" in html
    assert 'rel="noopener"' in html and 'enctype="multipart/form-data"' in html


# ---------- Excluir ----------
def test_delete_removes_record_and_files(app, auth_client, project):
    ref = _saved_ref(app, auth_client, project)
    assert len(stored_files(app)) == 2
    assert auth_client.get(f"/projetos/{project.id}/referencias/{ref.id}/excluir").status_code == 405
    assert auth_client.post(f"/projetos/{project.id}/referencias/{ref.id}/excluir").status_code == 302
    assert ProjectReference.query.count() == 0 and stored_files(app) == []
    assert ActivityLog.query.filter_by(action="deleted", entity_id=project.id).count() == 1


def test_delete_button_asks_for_confirmation(app, auth_client, project):
    _saved_ref(app, auth_client, project)
    assert "data-confirm=" in auth_client.get(f"/projetos/{project.id}").get_data(as_text=True)
