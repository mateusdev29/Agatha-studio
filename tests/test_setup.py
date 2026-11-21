"""Inicialização e login: banco novo/existente, usuário novo/existente, repetição, reinício e sessão."""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from flask import Flask

import bootstrap
from app import _ensure_secret_key, create_app
from app.extensions import db, login_manager
from app.models import Client, User
from app.services import setup_service as svc
from config import BASE_DIR

EXAMPLE = (BASE_DIR / ".env.example").read_text(encoding="utf-8")


# ------------------------------------------------------------------ bootstrap (.env)
def test_env_is_created_from_example_with_secret_and_password(tmp_path):
    env = tmp_path / ".env"
    r = bootstrap.ensure_env(env, BASE_DIR / ".env.example")
    text = env.read_text(encoding="utf-8")
    assert r["created_env"] and r["secret_key_created"] and r["password_created"]              # senha gerada aleatoriamente
    assert re.fullmatch(r"[0-9a-f]{64}", bootstrap.get_value(text, "SECRET_KEY"))
    assert bootstrap.get_value(text, "DEV_ADMIN_EMAIL") == "agatha@example.com"
    assert bootstrap.get_value(text, "DEV_ADMIN_PASSWORD") == r["password_created"]
    assert not text.startswith("\ufeff")


def test_env_second_run_changes_nothing(tmp_path):
    env = tmp_path / ".env"; bootstrap.ensure_env(env, BASE_DIR / ".env.example"); before = env.read_bytes()
    r = bootstrap.ensure_env(env, BASE_DIR / ".env.example")
    assert env.read_bytes() == before and r["password_created"] is None and not r["secret_key_created"] and not r["updated"]


def test_env_keeps_user_values_comments_and_crlf(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"# meu comentario\r\nAPP_ENV=development\r\nSECRET_KEY=\r\nDEV_ADMIN_EMAIL=eu@exemplo.com\r\nDEV_ADMIN_NAME=\r\nDEV_ADMIN_PASSWORD=minha-senha-forte-1\r\nOUTRA=valor\r\n")
    r = bootstrap.ensure_env(env, BASE_DIR / ".env.example")
    raw = env.read_bytes().decode()
    assert "# meu comentario" in raw and "OUTRA=valor" in raw and "minha-senha-forte-1" in raw and "eu@exemplo.com" in raw
    assert "\r\n" in raw and "\n" not in raw.replace("\r\n", "")            # continua CRLF
    assert r["password_created"] is None and r["secret_key_created"] and r["updated"]["DEV_ADMIN_NAME"] == "Agatha Souza"


def test_env_with_bom_is_read_correctly(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes("\ufeffAPP_ENV=development\nSECRET_KEY=abc123\nDEV_ADMIN_EMAIL=a@b.co\nDEV_ADMIN_NAME=A\nDEV_ADMIN_PASSWORD=senha-bem-longa\n".encode("utf-8"))
    r = bootstrap.ensure_env(env, BASE_DIR / ".env.example")
    assert not r["updated"] and not r["secret_key_created"]                   # APP_ENV foi lido apesar do BOM


def test_env_is_not_touched_in_production(tmp_path):
    env = tmp_path / ".env"; env.write_text("APP_ENV=production\nSECRET_KEY=\nDEV_ADMIN_PASSWORD=\n", encoding="utf-8")
    r = bootstrap.ensure_env(env, BASE_DIR / ".env.example")
    assert not r["development"] and r["password_created"] is None and env.read_text() == "APP_ENV=production\nSECRET_KEY=\nDEV_ADMIN_PASSWORD=\n"


def test_get_and_set_value_helpers():
    t = "# SECRET_KEY=comentario\nA=1\nB = \"dois\"\n"
    assert bootstrap.get_value(t, "B") == "dois" and bootstrap.get_value(t, "SECRET_KEY") is None
    t2 = bootstrap.set_value(t, "SECRET_KEY", "x"); assert t2.count("SECRET_KEY=x") == 1 and "# SECRET_KEY=comentario" in t2


def test_find_free_port_skips_busy_ports():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(); busy = s.getsockname()[1]
    try:
        assert bootstrap.find_free_port(busy) != busy
    finally:
        s.close()


# ------------------------------------------------------------------ fábrica de apps com banco temporário
@pytest.fixture()
def env_app(tmp_path, monkeypatch):
    from config import DevelopmentConfig
    folder = tmp_path / "pasta com espaço e ação"; folder.mkdir()          # caminho "difícil" do Windows
    dbf, envf = folder / "studio.db", folder / ".env"
    for k, v in {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbf.as_posix()}", "SECRET_KEY": "k" * 48, "ENV_FILE": str(envf)}.items():
        monkeypatch.setattr(DevelopmentConfig, k, v)
    monkeypatch.chdir(tmp_path)                                            # `flask setup` não depende da pasta atual
    for k in ("DEV_ADMIN_EMAIL", "DEV_ADMIN_NAME", "DEV_ADMIN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    envf.write_text("APP_ENV=development\nSECRET_KEY=" + "k" * 48 + "\nDEV_ADMIN_NAME=Agatha Souza\nDEV_ADMIN_EMAIL=agatha@example.com\nDEV_ADMIN_PASSWORD=senha-do-env-123\n", encoding="utf-8")

    class H:
        db_file, env_file, folder_ = dbf, envf, folder

        @staticmethod
        def app():
            return create_app("development")

        @staticmethod
        def run(app, cmd="setup"):
            return app.test_cli_runner().invoke(args=[cmd])
    return H


def users_snapshot(app):
    with app.app_context():
        return [(u.id, u.email, u.role, u.password_hash) for u in User.query.order_by(User.id)]


def test_setup_with_no_database_creates_everything(env_app):
    app = env_app.app(); assert not env_app.db_file.exists()
    r = env_app.run(app)
    assert r.exit_code == 0, r.output
    assert env_app.db_file.exists() and "Banco novo" in r.output and "Administradora criada: agatha@example.com" in r.output and "Sistema pronto" in r.output
    with app.app_context():
        assert svc.schema_state()[0] == "ok"
        u = User.query.one()
        assert (u.email, u.role, u.name) == ("agatha@example.com", "admin", "Agatha Souza")
        assert u.check_password("senha-do-env-123") and "senha-do-env-123" not in u.password_hash
        from app.models import BodyRegion, AnamnesisTemplate
        assert BodyRegion.query.count() == 13 and AnamnesisTemplate.query.count() == 8


def test_setup_is_idempotent_and_never_touches_existing_data(env_app):
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        db.session.add(Client(name="Cliente Importante")); db.session.commit()
    before = users_snapshot(app); size = env_app.db_file.stat().st_size
    for _ in range(3):
        r = env_app.run(app)
        assert r.exit_code == 0 and "nada a migrar" in r.output and "já existe" in r.output and "criada: " not in r.output
    assert users_snapshot(app) == before                                   # mesmo id, mesmo hash: nada foi recriado
    with app.app_context():
        assert Client.query.filter_by(name="Cliente Importante").count() == 1 and User.query.count() == 1
    assert not (env_app.db_file.parent / "backups").exists()               # sem migração pendente: sem backup


def test_existing_admin_is_never_overwritten_even_if_env_changes(env_app):
    app = env_app.app(); env_app.run(app); before = users_snapshot(app)
    env_app.env_file.write_text(env_app.env_file.read_text().replace("agatha@example.com", "outra@exemplo.com").replace("senha-do-env-123", "senha-totalmente-nova-9"), encoding="utf-8")
    app2 = env_app.app(); r = env_app.run(app2)
    assert r.exit_code == 0 and "já existe (agatha@example.com)" in r.output
    assert users_snapshot(app2) == before


def test_command_init_is_an_alias(env_app):
    r = env_app.run(env_app.app(), "init")
    assert r.exit_code == 0 and "Sistema pronto" in r.output


def test_existing_non_admin_user_with_same_email_is_not_modified(env_app):
    app = env_app.app()
    with app.app_context():
        db.create_all()                                                   # só para semear o usuário; setup trata o resto
    app.test_cli_runner()
    with app.app_context():
        db.drop_all()
    env_app.run(app)                                                      # banco normal
    with app.app_context():
        User.query.delete(); u = User(name="Func", email="agatha@example.com", role="staff"); u.set_password("senha-da-func-1"); db.session.add(u); db.session.commit()
    before = users_snapshot(app)
    r = env_app.run(app)
    assert r.exit_code != 0 and "não é um administrador ativo" in r.output
    assert users_snapshot(app) == before


@pytest.mark.parametrize("pw,email,msg", [("curta", "a@b.co", "pelo menos 10"), ("senha-longa-ok-1", "sem-arroba", "inválido")])
def test_invalid_env_values_fail_clearly_without_creating_user(env_app, pw, email, msg):
    text = env_app.env_file.read_text().replace("senha-do-env-123", pw).replace("agatha@example.com", email)
    env_app.env_file.write_text(text, encoding="utf-8")
    app = env_app.app(); r = env_app.run(app)
    assert r.exit_code != 0 and msg in r.output
    with app.app_context():
        assert User.query.count() == 0


def test_blank_password_in_env_is_generated_once_and_persisted(env_app):
    env_app.env_file.write_text(env_app.env_file.read_text().replace("senha-do-env-123", ""), encoding="utf-8")
    app = env_app.app(); r1 = env_app.run(app)
    pw = bootstrap.get_value(env_app.env_file.read_text(), "DEV_ADMIN_PASSWORD")
    assert r1.exit_code == 0 and len(pw) >= 10 and pw in r1.output
    with app.app_context():
        assert User.query.one().check_password(pw)
    r2 = env_app.run(app)
    assert pw not in r2.output and bootstrap.get_value(env_app.env_file.read_text(), "DEV_ADMIN_PASSWORD") == pw   # não troca nem reexibe


def test_database_without_migration_control_is_refused_and_untouched(env_app):
    con = sqlite3.connect(env_app.db_file); con.execute("CREATE TABLE minhas_coisas (id INTEGER, nome TEXT)"); con.execute("INSERT INTO minhas_coisas VALUES (1, 'precioso')"); con.commit(); con.close()
    r = env_app.run(env_app.app())
    assert r.exit_code != 0 and "não tem controle de migrations" in r.output and "Nada foi alterado" in r.output or "nada foi alterado" in r.output
    con = sqlite3.connect(env_app.db_file)
    assert con.execute("SELECT nome FROM minhas_coisas").fetchall() == [("precioso",)]
    assert con.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchall() == []
    con.close()


def test_pending_migration_makes_backup_before_upgrading(env_app, monkeypatch):
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        db.session.add(Client(name="Antes da atualização")); db.session.commit()
    calls = []
    monkeypatch.setattr(svc, "schema_state", lambda: ("pending", "antiga", "nova"))
    monkeypatch.setattr(svc, "upgrade", lambda **k: calls.append(sorted((env_app.db_file.parent / "backups").glob("*.db"))))
    r = env_app.run(app)
    assert r.exit_code == 0 and "Backup do banco antes de atualizar" in r.output
    assert len(calls) == 1 and len(calls[0]) == 1                          # o backup já existia quando a migração rodou
    con = sqlite3.connect(calls[0][0]); assert con.execute("SELECT name FROM clients").fetchall() == [("Antes da atualização",)]; con.close()


def test_backups_are_pruned(tmp_path):
    f = tmp_path / "studio.db"; con = sqlite3.connect(f); con.execute("CREATE TABLE t (x)"); con.commit(); con.close()
    for i in range(8):
        (tmp_path / "backups").mkdir(exist_ok=True); (tmp_path / "backups" / f"studio-2020010{i}-000000.db").write_bytes(b"x")
    new = svc.backup_database(f, keep=5)
    kept = sorted((tmp_path / "backups").glob("studio-*.db"))
    assert len(kept) == 5 and new in kept and sqlite3.connect(new).execute("SELECT count(*) FROM t").fetchone() == (0,)


def test_production_does_not_create_admin(tmp_path, monkeypatch):
    from config import ProductionConfig
    dbf = tmp_path / "p.db"
    for k, v in {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbf.as_posix()}", "SECRET_KEY": "k" * 48, "ENV_FILE": str(tmp_path / ".env")}.items():
        monkeypatch.setattr(ProductionConfig, k, v)
    (tmp_path / ".env").write_text("APP_ENV=production\nDEV_ADMIN_PASSWORD=senha-do-env-123\n"); monkeypatch.chdir(tmp_path)
    app = create_app("production"); r = app.test_cli_runner().invoke(args=["setup"])
    assert r.exit_code == 0 and "create-user" in r.output
    with app.app_context():
        assert User.query.count() == 0


# ------------------------------------------------------------------ login, sessão e reinício
def _login(client, email, password):
    """Login como o navegador faz: busca o formulário, usa o token CSRF e posta (CSRF está ATIVO em desenvolvimento)."""
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    return client.post("/login", data={"email": email, "password": password, "csrf_token": token})


def test_login_after_setup_correct_and_wrong_password(env_app):
    app = env_app.app(); env_app.run(app); c = app.test_client()
    bad = _login(c, "agatha@example.com", "senha-errada-123")
    assert bad.status_code == 200 and "E-mail ou senha incorretos." in bad.get_data(as_text=True) and c.get("/clientes/").status_code == 302
    ok = _login(c, "AGATHA@example.com", "senha-do-env-123")
    assert ok.status_code == 302 and c.get("/clientes/").status_code == 200


def test_session_survives_server_restart_but_not_a_different_secret_key(env_app, monkeypatch):
    from config import DevelopmentConfig
    app1 = env_app.app(); env_app.run(app1); c1 = app1.test_client(); _login(c1, "agatha@example.com", "senha-do-env-123")
    cookie = c1.get_cookie("agatha_studio_session"); assert cookie and c1.get("/clientes/").status_code == 200
    app2 = env_app.app()                                                     # "reiniciou o servidor": novo processo, mesma SECRET_KEY e mesmo banco
    c2 = app2.test_client(); c2.set_cookie("agatha_studio_session", cookie.value, domain="localhost")
    assert c2.get("/clientes/").status_code == 200
    monkeypatch.setattr(DevelopmentConfig, "SECRET_KEY", "z" * 48)           # chave diferente (o problema antigo)
    c3 = create_app("development").test_client(); c3.set_cookie("agatha_studio_session", cookie.value, domain="localhost")
    assert c3.get("/clientes/").status_code == 302


def test_cookie_names_and_session_protection(env_app):
    app = env_app.app(); env_app.run(app); c = app.test_client(); r = _login(c, "agatha@example.com", "senha-do-env-123")
    names = [h.split("=")[0] for h in r.headers.getlist("Set-Cookie")]
    assert "agatha_studio_session" in names and "session" not in names
    assert app.config["REMEMBER_COOKIE_NAME"] == "agatha_studio_remember" and login_manager.session_protection == "basic"


# ------------------------------------------------------------------ SECRET_KEY e config
def test_dev_secret_key_is_persistent_across_processes(tmp_path):
    def fresh():
        a = Flask("x", instance_path=str(tmp_path)); a.config.update(SECRET_KEY=None, REQUIRE_SECRET_KEY=False); _ensure_secret_key(a); return a.config["SECRET_KEY"]
    k1, k2 = fresh(), fresh()
    assert k1 == k2 and re.fullmatch(r"[0-9a-f]{64}", k1) and (tmp_path / "dev_secret_key").read_text() == k1


def test_secret_key_from_env_wins_and_production_requires_it(tmp_path):
    a = Flask("x", instance_path=str(tmp_path)); a.config.update(SECRET_KEY="do-env", REQUIRE_SECRET_KEY=False); _ensure_secret_key(a)
    assert a.config["SECRET_KEY"] == "do-env" and not (tmp_path / "dev_secret_key").exists()
    b = Flask("y", instance_path=str(tmp_path)); b.config.update(SECRET_KEY=None, REQUIRE_SECRET_KEY=True)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _ensure_secret_key(b)


def test_config_reads_env_file_with_bom(tmp_path):
    shutil.copy(BASE_DIR / "config.py", tmp_path / "config.py")
    (tmp_path / ".env").write_bytes("\ufeffSECRET_KEY=chave-com-bom\nAPP_ENV=development\n".encode("utf-8"))
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "APP_ENV", "DATABASE_URL")}
    out = subprocess.run([sys.executable, "-c", "import config; print(config.Config.SECRET_KEY)"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "chave-com-bom", out.stderr


def test_default_sqlite_uri_uses_forward_slashes():
    from config import Config
    assert "\\" not in Config.SQLALCHEMY_DATABASE_URI and Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///")


def test_sqlite_keeps_foreign_keys_on_and_stays_a_single_file(env_app):
    """Sem WAL: o banco é UM arquivo (copiar studio.db com o servidor parado não perde dados)."""
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        assert db.session.execute(db.text("PRAGMA foreign_keys")).scalar() == 1
        assert db.session.execute(db.text("PRAGMA journal_mode")).scalar().lower() == "delete"
        db.session.add(Client(name="Gravado")); db.session.commit()
    assert not list(env_app.db_file.parent.glob("studio.db-*"))
    only_the_file = sqlite3.connect(env_app.db_file)                       # lê só o .db, sem arquivos auxiliares
    assert only_the_file.execute("SELECT name FROM clients").fetchall() == [("Gravado",)]; only_the_file.close()


def test_backup_command_makes_a_consistent_copy(env_app):
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        db.session.add(Client(name="No backup")); db.session.commit()
    r = env_app.run(app, "backup")
    files = list((env_app.db_file.parent / "backups").glob("*.db"))
    assert r.exit_code == 0 and "Backup criado" in r.output and len(files) == 1
    c = sqlite3.connect(files[0]); assert c.execute("SELECT name FROM clients").fetchall() == [("No backup",)]; c.close()


def test_start_bat_is_windows_safe_and_runs_the_expected_steps():
    """cmd.exe exige CRLF (LF puro quebra labels/goto) e o console legado não gosta de acentos."""
    raw = (BASE_DIR / "start.bat").read_bytes()
    assert raw.count(b"\r\n") > 50 and raw.replace(b"\r\n", b"").count(b"\n") == 0 and all(b < 128 for b in raw)
    text = raw.decode("ascii")
    for needle in ("cd /d \"%~dp0\"", "py -3", "-m venv .venv", "bootstrap.py", "-m flask --app wsgi setup", "http://127.0.0.1:%PORT%", "--host 127.0.0.1"):
        assert needle in text, needle
    order = [text.index(x) for x in ("-m venv .venv", "pip install", "bootstrap.py\r\n", "wsgi setup", "wsgi run")]
    assert order == sorted(order)                                            # venv, deps, .env, setup, servidor
    assert "flask db upgrade" not in text and "seed-dev-user" not in text    # nada manual/destrutivo
    assert (BASE_DIR / ".gitattributes").read_text().count("eol=crlf") == 1


def test_reset_password_is_explicit_and_safe(env_app):
    app = env_app.app(); env_app.run(app); runner = app.test_cli_runner()
    with app.app_context():
        u = User.query.one(); u.failed_login_count, u.locked_until = 7, __import__("datetime").datetime(2999, 1, 1); db.session.commit()
    bad = runner.invoke(args=["reset-password"], input="ninguem@exemplo.com\nnova-senha-boa-1\nnova-senha-boa-1\n")
    assert bad.exit_code != 0 and "Nenhuma conta" in bad.output
    short = runner.invoke(args=["reset-password"], input="agatha@example.com\ncurta\ncurta\n")
    assert short.exit_code != 0 and "10 caracteres" in short.output
    ok = runner.invoke(args=["reset-password"], input="agatha@example.com\nnova-senha-boa-1\nnova-senha-boa-1\n")
    assert ok.exit_code == 0 and "redefinida" in ok.output
    with app.app_context():
        u = User.query.one()
        assert u.check_password("nova-senha-boa-1") and not u.check_password("senha-do-env-123") and u.failed_login_count == 0 and u.locked_until is None
        assert "nova-senha-boa-1" not in u.password_hash
    assert env_app.run(app).exit_code == 0                                   # e o setup seguinte NÃO desfaz a redefinição
    with app.app_context():
        assert User.query.one().check_password("nova-senha-boa-1")


def test_setup_upgrades_an_old_database_with_backup_and_keeps_every_row(env_app):
    """O caminho real de quem já usa o sistema: banco no schema ANTERIOR + dados -> setup migra com backup, sem perder nada."""
    from flask_migrate import upgrade
    app = env_app.app()
    with app.app_context():
        upgrade(directory=app.config["MIGRATIONS_DIR"], revision="9a714bbdb957")                 # schema de antes do sinal
    con = sqlite3.connect(env_app.db_file)
    con.execute("INSERT INTO clients (id,name,created_at,updated_at) VALUES (1,'Marina','2026-01-01','2026-01-01')")
    con.execute("INSERT INTO financial_transactions (type,description,amount_cents,date,client_id,status,created_at,updated_at) "
                "VALUES ('receita','Pagamento antigo',50000,'2026-02-01',1,'pago','2026-02-01','2026-02-01')")
    con.commit(); old_cols = [r[1] for r in con.execute("PRAGMA table_info(financial_transactions)")]; con.close()
    assert "appointment_id" not in old_cols

    r = env_app.run(app)
    assert r.exit_code == 0 and "Backup do banco antes de atualizar" in r.output and "9a714bbdb957 ->" in r.output
    backups = list((env_app.db_file.parent / "backups").glob("*.db")); assert len(backups) == 1
    b = sqlite3.connect(backups[0])
    assert "appointment_id" not in [x[1] for x in b.execute("PRAGMA table_info(financial_transactions)")]           # backup = schema antigo
    assert b.execute("SELECT description FROM financial_transactions").fetchall() == [("Pagamento antigo",)]; b.close()

    n = sqlite3.connect(env_app.db_file)
    assert {"appointment_id", "is_deposit"} <= {x[1] for x in n.execute("PRAGMA table_info(financial_transactions)")}
    assert n.execute("SELECT description,amount_cents,is_deposit,appointment_id FROM financial_transactions").fetchall() == [("Pagamento antigo", 50000, 0, None)]
    assert n.execute("SELECT name FROM clients").fetchall() == [("Marina",)]; n.close()
    with app.app_context():
        assert svc.schema_state()[0] == "ok" and User.query.count() == 1
    again = env_app.run(app)
    assert "nada a migrar" in again.output and len(list((env_app.db_file.parent / "backups").glob("*.db"))) == 1   # sem novo backup


# ------------------------------------------------------------------ login de desenvolvimento
def test_shipped_env_example_generates_a_valid_login():
    from email_validator import validate_email
    ex = (BASE_DIR / ".env.example").read_text(encoding="utf-8")
    email, pw = bootstrap.get_value(ex, "DEV_ADMIN_EMAIL"), bootstrap.get_value(ex, "DEV_ADMIN_PASSWORD")
    assert validate_email(email, check_deliverability=False) and not pw
    assert "gera" in ex.lower()                                              # o aviso sobre senha aleatória está documentado


def test_fresh_install_logs_in_with_the_generated_password(tmp_path, monkeypatch):
    """Instalação nova: copia o .env.example de verdade, gera uma senha e entra com ela."""
    from config import DevelopmentConfig
    env = tmp_path / ".env"; dbf = tmp_path / "studio.db"
    shutil.copy(BASE_DIR / ".env.example", env)
    for k, v in {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbf.as_posix()}", "SECRET_KEY": "k" * 48, "ENV_FILE": str(env)}.items():
        monkeypatch.setattr(DevelopmentConfig, k, v)
    for k in ("DEV_ADMIN_EMAIL", "DEV_ADMIN_NAME", "DEV_ADMIN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    app = create_app("development")
    assert app.test_cli_runner().invoke(args=["setup"]).exit_code == 0
    password = bootstrap.get_value(env.read_text(encoding="utf-8"), "DEV_ADMIN_PASSWORD")
    c = app.test_client(); assert _login(c, "agatha@example.com", password).status_code == 302 and c.get("/clientes/").status_code == 200


def _set_login(env_app, **env):
    text = env_app.env_file.read_text()
    for k, v in env.items():
        text = bootstrap.set_value(text, k, v)
    env_app.env_file.write_text(text, encoding="utf-8")
    app = env_app.app(); return app, env_app.run(app, "set-login")


def test_set_login_fixes_an_existing_account_with_an_unknown_password(env_app):
    """O problema real: banco antigo, usuário já existente, senha esquecida. `set-login` aplica a do .env."""
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        u = User.query.one(); u.set_password("senha-que-ninguem-lembra-9"); u.failed_login_count = 9
        from app.models.base import utcnow; from datetime import timedelta; u.locked_until = utcnow() + timedelta(days=1); db.session.commit(); uid = u.id
    c = app.test_client(); assert _login(c, "agatha@example.com", "senha-do-env-123").status_code == 200       # antes: não entra (nem destravada)
    app, r = _set_login(env_app)
    assert r.exit_code == 0 and "Senha aplicada à conta existente: agatha@example.com" in r.output
    with app.app_context():
        u = User.query.one(); assert u.id == uid and u.check_password("senha-do-env-123") and u.failed_login_count == 0 and u.locked_until is None
    c = app.test_client(); assert _login(c, "agatha@example.com", "senha-do-env-123").status_code == 302 and c.get("/clientes/").status_code == 200


def test_set_login_is_idempotent_and_does_not_rewrite_the_hash(env_app):
    app = env_app.app(); env_app.run(app); before = users_snapshot(app)
    r1 = env_app.run(app, "set-login"); r2 = env_app.run(app, "set-login")
    assert "Nada a alterar" in r1.output and "Nada a alterar" in r2.output and users_snapshot(app) == before


def test_set_login_with_a_new_email_updates_the_single_account_keeping_its_data(env_app):
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        db.session.add(Client(name="Dado preservado")); db.session.commit(); uid = User.query.one().id
    app, r = _set_login(env_app, DEV_ADMIN_EMAIL="nova@exemplo.com", DEV_ADMIN_NAME="Nova Dona", DEV_ADMIN_PASSWORD="outra-senha-forte-7")
    assert r.exit_code == 0 and "passou a usar este e-mail" in r.output
    with app.app_context():
        u = User.query.one()
        assert (u.id, u.email, u.name, u.role) == (uid, "nova@exemplo.com", "Nova Dona", "admin") and u.check_password("outra-senha-forte-7")
        assert Client.query.filter_by(name="Dado preservado").count() == 1
    assert _login(app.test_client(), "nova@exemplo.com", "outra-senha-forte-7").status_code == 302


def test_set_login_creates_the_account_when_there_is_none_and_reactivates_a_disabled_one(env_app):
    app = env_app.app(); env_app.run(app)
    with app.app_context():
        User.query.delete(); db.session.commit()
    app, r = _set_login(env_app); assert "Conta criada" in r.output
    with app.app_context():
        u = User.query.one(); u.is_active_flag, u.role = False, "staff"; db.session.commit()
    app, r = _set_login(env_app)
    with app.app_context():
        u = User.query.one(); assert u.is_active_flag and u.role == "admin" and r.exit_code == 0


def test_set_login_validates_and_is_blocked_in_production(env_app, tmp_path, monkeypatch):
    for over, msg in [({"DEV_ADMIN_PASSWORD": "curta"}, "pelo menos 10"), ({"DEV_ADMIN_EMAIL": "sem-arroba"}, "inválido")]:
        before = users_snapshot(env_app.app()) if env_app.db_file.exists() else None
        app, r = _set_login(env_app, **over)
        assert r.exit_code != 0 and msg in r.output
        if before is not None:
            assert users_snapshot(app) == before                                                       # erro nunca altera a conta
    from config import ProductionConfig
    for k, v in {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'p.db').as_posix()}", "SECRET_KEY": "k" * 48, "ENV_FILE": str(tmp_path / ".env")}.items():
        monkeypatch.setattr(ProductionConfig, k, v)
    (tmp_path / ".env").write_text("APP_ENV=production\n")
    r = create_app("production").test_cli_runner().invoke(args=["set-login"])
    assert r.exit_code != 0 and "bloqueado" in r.output


def test_start_scripts_expose_the_login_command_and_show_the_login_email():
    for name in ("start.bat", "start.sh"):
        text = (BASE_DIR / name).read_text(encoding="ascii")
        assert "set-login" in text and "bootstrap.py info" in text and "login" in text, name
    assert bootstrap.main(["bootstrap.py", "info"]) == 0


def test_bootstrap_info_prints_the_email_from_env(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").write_text("DEV_ADMIN_EMAIL=minha@conta.com\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    bootstrap.main(["bootstrap.py", "info"]); out = capsys.readouterr().out
    assert "minha@conta.com" in out and "start.bat login" in out and "DEV_ADMIN_PASSWORD" in out
