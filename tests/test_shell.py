import re
from datetime import datetime, time, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import (Appointment, Client, FinancialTransaction, InventoryItem, Project, Quote)
from app.models.enums import (AppointmentStatus, ProjectStatus, QuoteStatus, TransactionStatus,
                              TransactionType)
from app.navigation import all_items
from app.utils.dates import now_local, today_local
from app.utils.formatting import format_brl, format_date_long, month_year


def _client(name="Cliente Teste"):
    c = Client(name=name)
    db.session.add(c)
    db.session.flush()
    return c


# ---------- Navegação e casca ----------
def test_sidebar_lists_all_twelve_modules_in_order(auth_client):
    html = auth_client.get("/").get_data(as_text=True)
    labels = [i.label for i in all_items()]
    assert len(labels) == 12
    positions = [html.index(f'<span class="nav-label">{l}</span>') for l in labels]
    assert positions == sorted(positions)


def test_only_current_item_is_marked_active(auth_client):
    html = auth_client.get("/").get_data(as_text=True)
    assert html.count('aria-current="page"') == 1
    assert re.search(r'aria-current="page">\s*<svg[^>]*>.*?</svg><span class="nav-label">Visão Geral', html, re.S)


@pytest.mark.parametrize("item", all_items(), ids=lambda i: i.slug)
def test_every_module_route_exists_requires_login_and_marks_itself_active(client, login, item):
    assert client.get(item.path).status_code == 302                     # exige login
    login()
    r = client.get(item.path, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert f'title="{item.label}" aria-current="page"' in html          # destaca o próprio item e só ele
    assert html.count('aria-current="page"') >= 1


def test_topbar_has_user_name_avatar_and_logout_form(auth_client):
    html = auth_client.get("/").get_data(as_text=True)
    assert "Agatha Souza" in html and ">AS<" in html
    assert 'action="/logout"' in html and 'name="csrf_token"' in html


def test_rendered_pages_comply_with_csp(auth_client):
    """CSP proíbe estilos/scripts inline: nenhum template pode gerá-los."""
    for path in ("/", "/agenda", "/_ui"):
        html = auth_client.get(path).get_data(as_text=True)
        assert ' style="' not in html, path
        assert not re.search(r"<script(?![^>]*\bsrc=)", html), path
        assert not re.search(r"\son[a-z]+=\"", html), path


def test_ui_guide_exists_in_testing_but_not_in_production(auth_client, monkeypatch):
    assert auth_client.get("/_ui").status_code == 200
    from config import ProductionConfig
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "x")
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    prod = create_app("production")
    assert prod.test_client().get("/_ui").status_code == 404


def test_static_assets_are_served(client):
    for path in ("css/fonts.css", "css/tokens.css", "css/layout.css", "css/components.css",
                 "js/layout.js", "js/ui.js", "fonts/bodoni-moda-latin-wght-normal.woff2",
                 "fonts/instrument-sans-latin-wght-normal.woff2"):
        assert client.get(f"/static/{path}").status_code == 200, path


# ---------- Notificações ----------
def test_notifications_empty_state(auth_client):
    html = auth_client.get("/").get_data(as_text=True)
    assert "Tudo em dia" in html and 'class="count"' not in html


def test_notifications_come_from_database(app, auth_client):
    c = _client("Marina")
    now = now_local()
    db.session.add_all([
        Appointment(client_id=c.id, starts_at=now + timedelta(hours=24), status=AppointmentStatus.WAITING),
        Quote(client_id=c.id, description="x", status=QuoteStatus.SENT, valid_until=today_local() - timedelta(days=1)),
        InventoryItem(name="Agulha 7RL", quantity=2, min_quantity=5),
        InventoryItem(name="Tinta preta", quantity=1, min_quantity=1, expires_on=today_local() - timedelta(days=2)),
    ])
    db.session.commit()
    html = auth_client.get("/").get_data(as_text=True)
    assert "Confirmar atendimento de Marina" in html
    assert "Orçamento de Marina expirou" in html
    assert "Estoque baixo: Agulha 7RL" in html
    assert "Tinta preta vencido" in html
    # "Tinta preta" (quantidade = mínimo) é estoque baixo E vencida: 5 avisos no total
    assert "Estoque baixo: Tinta preta" in html
    assert '<span class="count" aria-hidden="true">5</span>' in html


def test_notifications_ignore_irrelevant_records(app, auth_client):
    c = _client()
    now = now_local()
    db.session.add_all([
        Appointment(client_id=c.id, starts_at=now + timedelta(hours=24), status=AppointmentStatus.CONFIRMED),
        Appointment(client_id=c.id, starts_at=now + timedelta(days=10), status=AppointmentStatus.WAITING),
        Quote(client_id=c.id, description="x", status=QuoteStatus.APPROVED, valid_until=today_local()),
        InventoryItem(name="Luvas", quantity=50, min_quantity=5),
        InventoryItem(name="Inativo", quantity=0, min_quantity=5, is_active=False),
    ])
    db.session.commit()
    assert "Tudo em dia" in auth_client.get("/").get_data(as_text=True)


# ---------- Visão Geral ----------
def test_overview_empty_states(auth_client):
    html = auth_client.get("/").get_data(as_text=True)
    assert "Nenhum atendimento à vista" in html
    assert "Sem lançamentos neste mês" in html
    assert "Agenda livre" in html


def test_overview_numbers_come_from_database(app, auth_client):
    c = _client()
    today = today_local()
    noon = datetime.combine(today, time(12))
    last_month = today.replace(day=1) - timedelta(days=1)
    db.session.add_all([
        Appointment(client_id=c.id, starts_at=noon, status=AppointmentStatus.CONFIRMED),
        Appointment(client_id=c.id, starts_at=noon, status=AppointmentStatus.CANCELED),  # não conta
        Project(client_id=c.id, name="A", status=ProjectStatus.IN_PROGRESS),
        Project(client_id=c.id, name="B", status=ProjectStatus.DONE),
        Quote(client_id=c.id, description="x", status=QuoteStatus.SENT),
        Quote(client_id=c.id, description="y", status=QuoteStatus.DRAFT),
        FinancialTransaction(type=TransactionType.INCOME, description="ok", amount_cents=100000, date=today,
                             status=TransactionStatus.PAID),
        FinancialTransaction(type=TransactionType.INCOME, description="pendente", amount_cents=999900, date=today,
                             status=TransactionStatus.PENDING),
        FinancialTransaction(type=TransactionType.INCOME, description="mês passado", amount_cents=777700,
                             date=last_month, status=TransactionStatus.PAID),
        FinancialTransaction(type=TransactionType.EXPENSE, description="mat", amount_cents=30050, date=today,
                             status=TransactionStatus.PAID),
    ])
    db.session.commit()

    from app.services.overview_service import get_overview
    ov = get_overview()
    assert ov.appointments_today == 1
    assert ov.projects_in_progress == 1
    assert ov.pending_quotes == 1
    assert ov.revenue_month_cents == 100000
    assert ov.expenses_month_cents == 30050
    assert ov.profit_month_cents == 69950

    html = auth_client.get("/").get_data(as_text=True)
    assert "R$ 1.000,00" in html and "R$ 300,50" in html and "R$ 699,50" in html
    assert "Sem lançamentos neste mês" not in html


def test_overview_negative_profit_is_flagged(app, auth_client):
    db.session.add(FinancialTransaction(type=TransactionType.EXPENSE, description="x", amount_cents=5000,
                                        date=today_local(), status=TransactionStatus.PAID))
    db.session.commit()
    html = auth_client.get("/").get_data(as_text=True)
    assert 'class="is-negative">-R$ 50,00' in html


# ---------- Formatação pt-BR ----------
@pytest.mark.parametrize("cents,expected", [
    (0, "R$ 0,00"), (5, "R$ 0,05"), (123456, "R$ 1.234,56"),
    (100000000, "R$ 1.000.000,00"), (-5000, "-R$ 50,00"), (None, "R$ 0,00"),
])
def test_format_brl(cents, expected):
    assert format_brl(cents) == expected


def test_date_formatting():
    from datetime import date
    assert format_date_long(date(2026, 9, 30)) == "quarta-feira, 30 de setembro"
    assert month_year(date(2026, 3, 1)) == "março de 2026"
