from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import (ActivityLog, Appointment, BodyRegion, Client, FinancialTransaction, Project, ProjectSession)
from app.models.enums import ProjectStatus, SessionStatus, TransactionStatus, TransactionType
from app.utils.dates import now_local, today_local


def mk_client(name="Marina Lopes", **kw):
    c = Client(name=name, **kw); db.session.add(c); db.session.commit(); return c


def mk_project(client, name="Floral", **kw):
    p = Project(client_id=client.id, name=name, **kw); db.session.add(p); db.session.commit(); return p


def form(client, **over):
    data = {"client_id": client.id, "name": "Floral antebraço", "style": "Fine line", "body_region_id": 0,
            "size": "15 cm", "price_cents": "1.200,50", "status": "orcamento", "description": "Peônias", "notes": ""}
    data.update(over); return data


# ---------- Acesso ----------
@pytest.mark.parametrize("method,path", [
    ("get", "/projetos/"), ("get", "/projetos/novo"), ("post", "/projetos/novo"), ("get", "/projetos/1"),
    ("get", "/projetos/1/editar"), ("get", "/projetos/1/sessoes/nova"), ("post", "/projetos/1/sessoes/1/excluir"),
    ("post", "/projetos/1/referencias"), ("get", "/projetos/1/referencias/1"), ("get", "/projetos/1/referencias/1/miniatura"),
    ("post", "/projetos/1/referencias/1/excluir"),
])
def test_all_routes_require_login(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# ---------- Criar ----------
def test_create_project(auth_client):
    c = mk_client()
    region = BodyRegion.query.filter_by(slug="antebraco").one()
    r = auth_client.post("/projetos/novo", data=form(c, body_region_id=region.id))
    assert r.status_code == 302
    p = Project.query.one()
    assert (p.client_id, p.price_cents, p.status, p.body_region_id) == (c.id, 120050, ProjectStatus.QUOTE, region.id)
    assert p.style == "Fine line" and p.notes is None
    assert ActivityLog.query.filter_by(action="created", entity_type="project", entity_id=p.id).count() == 1


def test_blank_price_becomes_zero_and_region_optional(auth_client):
    c = mk_client()
    auth_client.post("/projetos/novo", data=form(c, price_cents="", style=""))
    p = Project.query.one()
    assert p.price_cents == 0 and p.body_region_id is None and p.style is None


@pytest.mark.parametrize("over,message", [
    ({"name": ""}, "Informe o nome do projeto."),
    ({"price_cents": "abc"}, "Valor inválido"),
    ({"price_cents": "-10"}, "Valor inválido"),
    ({"style": "Inventado"}, "Not a valid choice"),
    ({"status": "xyz"}, "Not a valid choice"),
    ({"client_id": 9999}, "Not a valid choice"),
    ({"body_region_id": 9999}, "Not a valid choice"),
])
def test_create_validation(auth_client, over, message):
    c = mk_client()
    r = auth_client.post("/projetos/novo", data=form(c, **over))
    assert r.status_code == 400 and message in r.get_data(as_text=True)
    assert Project.query.count() == 0


def test_cannot_create_for_archived_client(auth_client):
    c = mk_client(archived_at=datetime(2026, 1, 1))
    assert auth_client.post("/projetos/novo", data=form(c)).status_code == 400
    assert Project.query.count() == 0


def test_client_preselected_from_query_string(auth_client):
    mk_client("Ana"); b = mk_client("Bia")
    html = auth_client.get(f"/projetos/novo?cliente={b.id}").get_data(as_text=True)
    assert f'<option selected value="{b.id}">Bia</option>' in html


def test_form_without_clients_shows_guidance(auth_client):
    assert "Cadastre um cliente primeiro" in auth_client.get("/projetos/novo").get_data(as_text=True)


def test_money_field_keeps_typed_text_on_error(auth_client):
    c = mk_client()
    html = auth_client.post("/projetos/novo", data=form(c, name="")).get_data(as_text=True)
    assert 'value="1.200,50"' in html


# ---------- Lista ----------
def test_list_empty_state(auth_client):
    assert "Nenhum projeto ainda" in auth_client.get("/projetos/").get_data(as_text=True)


def test_search_and_status_filter(auth_client):
    a, b = mk_client("Marina"), mk_client("Caio")
    mk_project(a, "Floral", style="Fine line", status=ProjectStatus.IN_PROGRESS)
    mk_project(b, "Leão", style="Realismo", status=ProjectStatus.DONE)
    get = lambda **q: auth_client.get("/projetos/", query_string=q).get_data(as_text=True)
    assert "Floral" in get(q="floral") and "Leão" not in get(q="floral")
    assert "Leão" in get(q="caio") and "Floral" not in get(q="caio")           # busca pelo cliente
    assert "Leão" in get(q="realismo") and "Floral" not in get(q="realismo")  # busca pelo estilo
    assert "Floral" in get(status="em_andamento") and "Leão" not in get(status="em_andamento")
    assert "Floral" in get(status="inventado") and "Leão" in get(status="inventado")   # inválido: ignora o filtro
    assert "Nenhum projeto encontrado" in get(q="zzz")


def test_search_wildcards_are_literal(auth_client):
    c = mk_client()
    mk_project(c, "Normal"); mk_project(c, "100% preto")
    html = auth_client.get("/projetos/", query_string={"q": "%"}).get_data(as_text=True)
    assert "100% preto" in html and "Normal" not in html


def test_pagination(auth_client):
    c = mk_client()
    for i in range(20):
        mk_project(c, f"Projeto {i:02d}")
    assert 'aria-label="Paginação"' in auth_client.get("/projetos/").get_data(as_text=True)
    assert auth_client.get("/projetos/?page=2").status_code == 200


# ---------- Detalhe e edição ----------
def test_detail_404(auth_client):
    assert auth_client.get("/projetos/999").status_code == 404


def test_detail_financials(auth_client):
    c = mk_client(); p = mk_project(c, price_cents=200000)
    today = today_local()
    db.session.add_all([
        ProjectSession(project_id=p.id, scheduled_at=now_local(), price_cents=50000),
        ProjectSession(project_id=p.id, scheduled_at=now_local(), price_cents=70000),
        ProjectSession(project_id=p.id, scheduled_at=now_local(), price_cents=99900, status=SessionStatus.CANCELED),
        FinancialTransaction(type=TransactionType.INCOME, description="a", amount_cents=30000, date=today,
                             project_id=p.id, status=TransactionStatus.PAID),
        FinancialTransaction(type=TransactionType.INCOME, description="b", amount_cents=40000, date=today,
                             project_id=p.id, status=TransactionStatus.PENDING),
        FinancialTransaction(type=TransactionType.EXPENSE, description="c", amount_cents=9000, date=today,
                             project_id=p.id, status=TransactionStatus.PAID),
    ])
    db.session.commit()
    html = auth_client.get(f"/projetos/{p.id}").get_data(as_text=True)
    assert "R$ 300,00" in html and "R$ 400,00" in html          # pago / a receber (despesa ignorada)
    assert "Sessões (2)" in html and "R$ 1.200,00" in html       # cancelada não conta
    assert "R$ 2.000,00" in html


def test_edit_project(auth_client):
    c = mk_client(); p = mk_project(c, "Antigo", status=ProjectStatus.QUOTE)
    html = auth_client.get(f"/projetos/{p.id}/editar").get_data(as_text=True)
    assert 'value="Antigo"' in html
    r = auth_client.post(f"/projetos/{p.id}/editar", data=form(c, name="Novo", status="em_andamento", price_cents="500"))
    assert r.status_code == 302
    db.session.refresh(p)
    assert (p.name, p.status, p.price_cents) == ("Novo", ProjectStatus.IN_PROGRESS, 50000)


def test_edit_keeps_archived_client_available(auth_client):
    c = mk_client(archived_at=datetime(2026, 1, 1)); p = mk_project(c)
    assert auth_client.post(f"/projetos/{p.id}/editar", data=form(c, name="Ajustado")).status_code == 302


def test_user_content_is_escaped(auth_client):
    c = mk_client("<b>Cliente</b>"); p = mk_project(c, "<script>alert(1)</script>", notes="<img src=x onerror=alert(1)>")
    for path in ("/projetos/", f"/projetos/{p.id}", f"/projetos/{p.id}/editar"):
        html = auth_client.get(path).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html and "<img src=x" not in html and "<b>Cliente</b>" not in html


def test_client_tab_links_to_projects(auth_client):
    c = mk_client(); p = mk_project(c, "Floral")
    html = auth_client.get(f"/clientes/{c.id}?aba=projetos").get_data(as_text=True)
    assert f'href="/projetos/{p.id}"' in html and f"/projetos/novo?cliente={c.id}" in html


def test_sidebar_marks_projects_active(auth_client):
    c = mk_client(); p = mk_project(c)
    assert 'href="/projetos" title="Projetos" aria-current="page"' in auth_client.get(f"/projetos/{p.id}").get_data(as_text=True)


# ---------- Sessões ----------
SESSION = {"scheduled_at": "2026-11-10T14:30", "duration_minutes": "180", "price_cents": "600,00", "status": "agendada", "notes": "Contorno"}


def test_session_crud(auth_client):
    c = mk_client(); p = mk_project(c)
    assert auth_client.post(f"/projetos/{p.id}/sessoes/nova", data=SESSION).status_code == 302
    s = ProjectSession.query.one()
    assert (s.scheduled_at, s.duration_minutes, s.price_cents) == (datetime(2026, 11, 10, 14, 30), 180, 60000)
    page_html = auth_client.get(f"/projetos/{p.id}").get_data(as_text=True)
    assert "10/11/2026" in page_html and "às 14:30 · 180 min" in page_html

    page = auth_client.get(f"/projetos/{p.id}/sessoes/{s.id}/editar").get_data(as_text=True)
    assert 'value="2026-11-10T14:30"' in page and 'value="600,00"' in page
    auth_client.post(f"/projetos/{p.id}/sessoes/{s.id}/editar", data={**SESSION, "status": "realizada", "price_cents": "650"})
    db.session.refresh(s)
    assert s.status == SessionStatus.DONE and s.price_cents == 65000

    assert auth_client.get(f"/projetos/{p.id}/sessoes/{s.id}/excluir").status_code == 405
    assert auth_client.post(f"/projetos/{p.id}/sessoes/{s.id}/excluir").status_code == 302
    assert ProjectSession.query.count() == 0


@pytest.mark.parametrize("over,message", [
    ({"scheduled_at": ""}, "Informe a data e o horário."),
    ({"scheduled_at": "1999-01-01T10:00"}, "Data inválida."),
    ({"duration_minutes": "5"}, "Use de 15 a 720 minutos."),
    ({"duration_minutes": "9999"}, "Use de 15 a 720 minutos."),
    ({"price_cents": "xx"}, "Valor inválido"),
    ({"status": "xyz"}, "Not a valid choice"),
])
def test_session_validation(auth_client, over, message):
    c = mk_client(); p = mk_project(c)
    r = auth_client.post(f"/projetos/{p.id}/sessoes/nova", data={**SESSION, **over})
    assert r.status_code == 400 and message in r.get_data(as_text=True)
    assert ProjectSession.query.count() == 0


def test_session_linked_to_appointment_cannot_be_deleted(auth_client):
    c = mk_client(); p = mk_project(c)
    s = ProjectSession(project_id=p.id, scheduled_at=now_local()); db.session.add(s); db.session.flush()
    db.session.add(Appointment(client_id=c.id, project_id=p.id, session_id=s.id, starts_at=now_local() + timedelta(days=1)))
    db.session.commit()
    r = auth_client.post(f"/projetos/{p.id}/sessoes/{s.id}/excluir", follow_redirects=True)
    assert "vinculada a um atendimento" in r.get_data(as_text=True)
    assert ProjectSession.query.count() == 1


def test_session_of_another_project_is_404(auth_client):
    c = mk_client(); p1, p2 = mk_project(c, "P1"), mk_project(c, "P2")
    s = ProjectSession(project_id=p1.id, scheduled_at=now_local()); db.session.add(s); db.session.commit()
    assert auth_client.get(f"/projetos/{p2.id}/sessoes/{s.id}/editar").status_code == 404
    assert auth_client.post(f"/projetos/{p2.id}/sessoes/{s.id}/excluir").status_code == 404
    assert ProjectSession.query.count() == 1
