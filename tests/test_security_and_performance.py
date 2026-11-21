"""Testes transversais: valem para TODAS as rotas registradas, inclusive as futuras."""
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import event

from app.extensions import db
from app.models import (AnamnesisResponse, Appointment, Category, Client, Evaluation, FinancialTransaction, InventoryItem,
                        Project, Quote)
from app.models.enums import AppointmentStatus, CategoryKind, QuoteStatus, TransactionStatus, TransactionType
from app.utils.dates import now_local, today_local

PUBLIC = {"static", "auth.login"}


def app_rules(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint not in PUBLIC:
            yield rule, rule.build({a: 1 for a in rule.arguments}, append_unknown=False)[1]


def methods(rule):
    return sorted(rule.methods - {"HEAD", "OPTIONS"})


def test_route_inventory_is_what_we_expect(app):
    rules = list(app_rules(app))
    assert len(rules) >= 65                                          # alguém removeu rotas sem querer?
    assert {"main.home", "clients.index", "projects.index", "quotes.index", "agenda.index", "finance.index", "stock.index",
            "anamnesis.index", "satisfaction.index", "body.body_map", "dashboard.dashboard", "settings.profile"} <= {r.endpoint for r, _ in rules}


def test_every_route_requires_login(app):
    """Nenhuma rota administrativa responde a quem não está logado."""
    anon = app.test_client()
    for rule, url in app_rules(app):
        for method in methods(rule):
            r = anon.open(url, method=method)
            assert r.status_code == 302 and "/login" in r.headers["Location"], f"{method} {url} ({rule.endpoint}) -> {r.status_code}"


def test_every_post_rejects_missing_csrf_token(app):
    app.config["WTF_CSRF_ENABLED"] = True
    anon = app.test_client()
    posts = [(rule, url) for rule, url in app_rules(app) if "POST" in rule.methods] + [(r, r.rule) for r in app.url_map.iter_rules() if r.endpoint == "auth.login"]
    assert len(posts) >= 40
    for rule, url in posts:
        assert anon.post(url).status_code == 400, f"POST {url} ({rule.endpoint}) aceitou requisição sem CSRF"


def test_state_changing_routes_do_not_accept_get(auth_client, app):
    for rule, url in app_rules(app):
        if methods(rule) == ["POST"]:
            assert auth_client.get(url).status_code == 405, f"GET {url} ({rule.endpoint}) não deveria existir"


def test_every_get_page_renders_without_server_error(auth_client, app):
    """Com dados de demonstração, nenhuma tela administrativa devolve erro 5xx."""
    from app.seeds.demo import seed_demo
    seed_demo()
    for rule, url in app_rules(app):
        if methods(rule) == ["GET"] or "GET" in rule.methods:
            r = auth_client.get(url)
            assert r.status_code < 500, f"GET {url} ({rule.endpoint}) -> {r.status_code}"
            assert "Traceback" not in r.get_data(as_text=True)


def test_security_headers_on_every_response_kind(auth_client):
    for path in ("/", "/login", "/nao-existe", "/static/css/tokens.css", "/dashboard/"):
        r = auth_client.get(path)
        assert r.headers["X-Content-Type-Options"] == "nosniff" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"], path
    assert "script-src 'self'" in auth_client.get("/").headers["Content-Security-Policy"]


def test_session_cookie_flags_in_production(monkeypatch):
    from app import create_app
    from config import ProductionConfig
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "x"); monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    cfg = create_app("production").config
    assert cfg["SESSION_COOKIE_SECURE"] and cfg["SESSION_COOKIE_HTTPONLY"] and cfg["SESSION_COOKIE_SAMESITE"] == "Lax" and not cfg["DEBUG"]


def test_foreign_keys_are_enforced(app):
    """SQLite ignora FK por padrão; o app liga o PRAGMA. Sem isso, dados órfãos passariam em silêncio."""
    from sqlalchemy.exc import IntegrityError
    db.session.add(Project(client_id=99999, name="Órfão"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_unhandled_errors_do_not_leak_internals(app, auth_client, monkeypatch):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    monkeypatch.setattr("app.routes.clients.svc.search_clients", lambda *a, **k: 1 / 0)
    r = auth_client.get("/clientes/")
    assert r.status_code == 500 and "ZeroDivision" not in r.get_data(as_text=True) and "Algo deu errado" in r.get_data(as_text=True)


# ---------- Desempenho: nenhuma lista pode fazer N+1 ----------
class QueryCounter:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        event.listen(db.engine, "before_cursor_execute", self._hit); return self

    def __exit__(self, *exc):
        event.remove(db.engine, "before_cursor_execute", self._hit)

    def _hit(self, *args):
        self.n += 1


def _queries(client, path):
    client.get(path)                                                 # aquecimento (gancho de expiração, caches)
    with QueryCounter() as q:
        assert client.get(path).status_code == 200
    return q.n


def _seed_clients(n):
    return [Client(name=f"Cliente {i:03d}") for i in range(n)]


def _fill(kind, start, count):
    c = Client(name="Base"); db.session.add(c); db.session.flush()
    cs = [Client(name=f"C{start + i}") for i in range(count)]; db.session.add_all(cs); db.session.flush()
    cat_in = Category.query.filter_by(kind=CategoryKind.INCOME).first(); cat_inv = Category.query.filter_by(kind=CategoryKind.INVENTORY).first()
    day = datetime.combine(today_local(), time(6))
    for i, x in enumerate(cs):
        if kind == "projetos":
            db.session.add(Project(client_id=x.id, name=f"P{start + i}"))
        elif kind == "orcamentos":
            db.session.add(Quote(client_id=x.id, description="d", price_cents=1000, status=QuoteStatus.SENT))
        elif kind == "agenda":
            db.session.add(Appointment(client_id=x.id, starts_at=day + timedelta(minutes=30 * (start + i)), duration_minutes=30, status=AppointmentStatus.WAITING))
        elif kind == "financeiro":
            db.session.add(FinancialTransaction(type=TransactionType.INCOME, description="d", amount_cents=100, date=today_local(), client_id=x.id, category_id=cat_in.id, status=TransactionStatus.PAID))
        elif kind == "estoque":
            db.session.add(InventoryItem(name=f"I{start + i}", quantity=1, category_id=cat_inv.id))
        elif kind == "satisfacao":
            db.session.add(Evaluation(client_id=x.id, score=8, evaluated_on=today_local()))
        elif kind == "anamnese":
            db.session.add(AnamnesisResponse(client_id=x.id, answers=[], accepted=True))
    db.session.commit()


@pytest.mark.parametrize("kind,path", [
    ("clientes", "/clientes/"), ("projetos", "/projetos/"), ("orcamentos", "/orcamentos/"), ("agenda", "/agenda/?vista=dia"),
    ("financeiro", "/financeiro/"), ("estoque", "/estoque/"), ("satisfacao", "/satisfacao/"), ("anamnese", "/anamnese/"),
])
def test_list_pages_do_not_have_n_plus_one(auth_client, kind, path):
    if kind == "clientes":
        db.session.add_all(_seed_clients(2)); db.session.commit()
    else:
        _fill(kind, 0, 2)
    few = _queries(auth_client, path)
    if kind == "clientes":
        db.session.add_all(_seed_clients(15)); db.session.commit()
    else:
        _fill(kind, 100, 14)
    many = _queries(auth_client, path)
    assert many - few <= 2, f"{path}: {few} consultas com 2 linhas, {many} com ~15 (N+1?)"
    assert many < 30
