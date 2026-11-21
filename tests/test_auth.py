import pytest
from app.extensions import db
from app.models import ActivityLog, User
from tests.conftest import TEST_PASSWORD


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Gest\xc3\xa3o do Est\xc3\xbadio" in r.data


def test_protected_page_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_login_success_and_access(client, login):
    r = login()
    assert r.status_code == 302
    assert client.get("/").status_code == 200


def test_login_is_case_insensitive_on_email(client, login):
    assert login(email="  AGATHA@example.com ").status_code == 302


def test_login_wrong_password_is_generic(client, login):
    r = login(password="errada")
    assert r.status_code == 200
    assert "E-mail ou senha incorretos." in r.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_unknown_email_same_message(client, login):
    r = login(email="ninguem@example.com")
    assert "E-mail ou senha incorretos." in r.get_data(as_text=True)


def test_empty_form_returns_validation_errors(client):
    r = client.post("/login", data={})
    assert r.status_code == 400
    assert "Informe o e-mail." in r.get_data(as_text=True)


def test_password_is_never_stored_in_plain_text(app):
    user = User.query.filter_by(email="agatha@example.com").one()
    assert user.password_hash != TEST_PASSWORD
    assert TEST_PASSWORD not in user.password_hash
    assert user.check_password(TEST_PASSWORD)


def test_account_locks_after_repeated_failures(app, client, login):
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        login(password="errada")
    # mesmo com a senha correta, fica bloqueada
    r = login()
    assert r.status_code == 200
    assert "Muitas tentativas" in r.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_successful_login_resets_failed_counter(app, login):
    login(password="errada")
    login()
    user = User.query.filter_by(email="agatha@example.com").one()
    assert user.failed_login_count == 0


def test_inactive_user_cannot_login(app, client, login):
    user = User.query.filter_by(email="agatha@example.com").one()
    user.is_active_flag = False
    db.session.commit()
    assert login().status_code == 200
    assert client.get("/").status_code == 302


def test_login_is_recorded_in_activity_log(app, login):
    login()
    assert ActivityLog.query.filter_by(action="login").count() == 1


def test_next_param_safe_redirect(client, login):
    r = login(query_string={"next": "/"})
    assert r.status_code == 302 and r.headers["Location"] == "/"


def test_next_param_blocks_open_redirect(client, login):
    r = login(query_string={"next": "https://evil.example.com/"})
    assert "evil.example.com" not in r.headers["Location"]


def test_logout_requires_post_and_ends_session(auth_client):
    assert auth_client.get("/logout").status_code == 405
    r = auth_client.post("/logout")
    assert r.status_code == 302
    assert auth_client.get("/").status_code == 302


def test_security_headers_present(client):
    r = client.get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_404_page_does_not_leak_internals(client):
    r = client.get("/nao-existe")
    assert r.status_code == 404
    assert "Traceback" not in r.get_data(as_text=True)


@pytest.mark.parametrize("ip2,ua2", [("10.0.0.2", "Mozilla/5.0 (iPhone)"), ("10.0.0.1", "Mozilla/5.0 (Android)")])
def test_session_survives_network_or_agent_change(app, ip2, ua2):
    """Celular troca de Wi-Fi/4G (IP muda) ou passa por proxy: a usuária não pode ser deslogada a cada clique."""
    from tests.conftest import TEST_PASSWORD
    c = app.test_client()
    with app.app_context():   # contexto novo: o `g` do Flask-Login vazaria o usuário entre requisições do teste
        c.post("/login", data={"email": "agatha@example.com", "password": TEST_PASSWORD},
               environ_base={"REMOTE_ADDR": "10.0.0.1"}, headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
    with app.app_context():
        r = c.get("/clientes/", environ_base={"REMOTE_ADDR": ip2}, headers={"User-Agent": ua2})
    assert r.status_code == 200, f"deslogada ao mudar rede/agente (status {r.status_code})"
