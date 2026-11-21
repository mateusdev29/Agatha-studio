import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.services.seed_base import seed_base

TEST_PASSWORD = "senha-de-teste-123"  # somente para testes


@pytest.fixture()
def app(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")   # nunca toca a pasta real
    with app.app_context():
        db.create_all()
        seed_base()
        user = User(name="Agatha Souza", email="agatha@example.com")
        user.set_password(TEST_PASSWORD)
        db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login(client):
    def _login(email="agatha@example.com", password=TEST_PASSWORD, **kwargs):
        return client.post("/login", data={"email": email, "password": password}, **kwargs)
    return _login


@pytest.fixture()
def auth_client(client, login):
    login()
    return client
