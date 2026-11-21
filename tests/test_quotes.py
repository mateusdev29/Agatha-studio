from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import ActivityLog, BodyRegion, Client, Project, Quote
from app.models.enums import ProjectStatus, QuoteStatus as S
from app.services import quote_service as svc
from app.utils.dates import today_local


def mk_client(name="Marina Lopes", **kw):
    c = Client(name=name, **kw); db.session.add(c); db.session.commit(); return c


def mk_quote(client, status=S.DRAFT, price=120000, valid=None, **kw):
    q = Quote(client_id=client.id, description=kw.pop("description", "Floral no antebraço"), status=status,
              price_cents=price, valid_until=valid if valid is not None else today_local() + timedelta(days=10), **kw)
    db.session.add(q); db.session.commit(); return q


def form(client, **over):
    data = {"client_id": client.id, "description": "Floral no antebraço", "style": "Fine line", "body_region_id": 0,
            "size": "15 cm", "price_cents": "1.200,00", "valid_until": (today_local() + timedelta(days=7)).isoformat(), "notes": "interno"}
    data.update(over); return data


def post(client, quote, action, **data):
    return client.post(f"/orcamentos/{quote.id}/{action}", data=data)


@pytest.mark.parametrize("method,path", [
    ("get", "/orcamentos/"), ("get", "/orcamentos/novo"), ("post", "/orcamentos/novo"), ("get", "/orcamentos/1"),
    ("get", "/orcamentos/1/editar"), ("post", "/orcamentos/1/status"), ("post", "/orcamentos/1/aprovar"),
    ("post", "/orcamentos/1/criar-projeto"), ("post", "/orcamentos/1/excluir"),
])
def test_all_routes_require_login(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# ---------- CRUD ----------
def test_create_starts_as_draft_with_default_validity(auth_client):
    c = mk_client()
    html = auth_client.get(f"/orcamentos/novo?cliente={c.id}").get_data(as_text=True)
    assert f'<option selected value="{c.id}">' in html
    assert (today_local() + timedelta(days=15)).isoformat() in html
    assert auth_client.post("/orcamentos/novo", data=form(c, status="aprovado")).status_code == 302   # status do POST é ignorado
    q = Quote.query.one()
    assert q.status == S.DRAFT and q.price_cents == 120000 and q.notes == "interno"
    assert ActivityLog.query.filter_by(action="created", entity_type="quote").count() == 1


@pytest.mark.parametrize("over,msg", [
    ({"description": ""}, "Descreva a tatuagem."), ({"price_cents": "x"}, "Valor inválido"),
    ({"valid_until": "2020-01-01"}, "não pode estar no passado"), ({"valid_until": "2101-01-01"}, "Data inválida"),
    ({"client_id": 999}, "Not a valid choice"), ({"style": "Nada"}, "Not a valid choice"),
])
def test_create_validation(auth_client, over, msg):
    c = mk_client()
    r = auth_client.post("/orcamentos/novo", data=form(c, **over))
    assert r.status_code == 400 and msg in r.get_data(as_text=True) and Quote.query.count() == 0


def test_archived_client_cannot_get_quote(auth_client):
    c = mk_client(archived_at=datetime(2026, 1, 1))
    assert auth_client.post("/orcamentos/novo", data=form(c)).status_code == 400


def test_edit_and_keep_past_validity_if_unchanged(auth_client):
    c = mk_client(); q = mk_quote(c, valid=today_local() - timedelta(days=3))
    r = auth_client.post(f"/orcamentos/{q.id}/editar", data=form(c, description="Nova", valid_until=q.valid_until.isoformat()))
    assert r.status_code == 302
    db.session.refresh(q); assert q.description == "Nova"
    assert auth_client.post(f"/orcamentos/{q.id}/editar", data=form(c, valid_until="2020-02-02")).status_code == 400


def test_list_search_filter_pagination(auth_client):
    a, b = mk_client("Marina"), mk_client("Caio")
    mk_quote(a, S.SENT, description="Floral", style="Fine line"); mk_quote(b, S.APPROVED, description="Leão", style="Realismo")
    get = lambda **q: auth_client.get("/orcamentos/", query_string=q).get_data(as_text=True)
    assert "Floral" in get(q="marina") and "Leão" not in get(q="marina")
    assert "Leão" in get(q="realismo") and "Floral" not in get(q="realismo")
    assert "Leão" in get(status="aprovado") and "Floral" not in get(status="aprovado")
    assert "Nenhum orçamento encontrado" in get(q="zzz")
    for i in range(20):
        mk_quote(a, description=f"Q{i}")
    assert 'aria-label="Paginação"' in get()


def test_empty_list_and_missing_clients(auth_client):
    assert "Nenhum orçamento ainda" in auth_client.get("/orcamentos/").get_data(as_text=True)
    assert "Cadastre um cliente primeiro" in auth_client.get("/orcamentos/novo").get_data(as_text=True)
    assert auth_client.get("/orcamentos/999").status_code == 404


def test_xss_is_escaped(auth_client):
    c = mk_client("<b>X</b>"); q = mk_quote(c, description="<script>alert(1)</script>", notes="<img src=x onerror=1>")
    for path in ("/orcamentos/", f"/orcamentos/{q.id}", f"/orcamentos/{q.id}/editar"):
        h = auth_client.get(path).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in h and "<img src=x" not in h and "<b>X</b>" not in h


# ---------- Máquina de estados ----------
def test_full_happy_path(auth_client):
    c = mk_client(); q = mk_quote(c)
    for action, status in [("status", "enviado"), ("status", "aguardando_resposta")]:
        assert post(auth_client, q, action, status=status).status_code == 302
    db.session.refresh(q); assert q.status == S.WAITING
    assert ActivityLog.query.filter_by(action="status", entity_id=q.id).count() == 2


@pytest.mark.parametrize("start,target", [
    (S.DRAFT, "aguardando_resposta"), (S.DRAFT, "recusado"), (S.SENT, "rascunho"), (S.WAITING, "enviado"),
    (S.REJECTED, "enviado"), (S.EXPIRED, "enviado"), (S.APPROVED, "rascunho"),
])
def test_invalid_transitions_are_blocked(auth_client, start, target):
    c = mk_client(); q = mk_quote(c, start)
    r = post(auth_client, q, "status", status=target)
    assert r.status_code == 302
    db.session.refresh(q); assert q.status == start


def test_status_cannot_be_set_to_approved_or_garbage_via_status_route(auth_client):
    c = mk_client(); q = mk_quote(c, S.SENT)
    post(auth_client, q, "status", status="aprovado"); post(auth_client, q, "status", status="lixo"); auth_client.post(f"/orcamentos/{q.id}/status")
    db.session.refresh(q); assert q.status == S.SENT


@pytest.mark.parametrize("target_route,data", [("status", {"status": "enviado"}), ("aprovar", {})])
def test_cannot_send_or_approve_without_price(auth_client, target_route, data):
    c = mk_client()
    q = mk_quote(c, S.DRAFT if target_route == "status" else S.SENT, price=0)
    r = auth_client.post(f"/orcamentos/{q.id}/{target_route}", data=data, follow_redirects=True)
    assert "Defina o valor" in r.get_data(as_text=True)
    db.session.refresh(q); assert q.status in (S.DRAFT, S.SENT)


def test_cannot_send_with_expired_validity(auth_client):
    c = mk_client(); q = mk_quote(c, S.DRAFT, valid=today_local() - timedelta(days=1))
    r = post(auth_client, q, "status", status="enviado"); db.session.refresh(q)
    assert q.status == S.DRAFT


def test_reopen_rejected_and_expired(auth_client):
    c = mk_client()
    for st in (S.REJECTED, S.EXPIRED):
        q = mk_quote(c, st); post(auth_client, q, "status", status="rascunho"); db.session.refresh(q)
        assert q.status == S.DRAFT


# ---------- Aprovação e projeto ----------
def test_approve_and_create_project_in_one_step(auth_client):
    c = mk_client(); region = BodyRegion.query.filter_by(slug="costas").one()
    q = mk_quote(c, S.SENT, style="Realismo", size="30 cm", body_region_id=region.id, notes="obs",
                 description="Leão realista\nCom coroa")
    r = post(auth_client, q, "aprovar", create_project="1")
    p = Project.query.one()
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/projetos/{p.id}")
    db.session.refresh(q)
    assert q.status == S.APPROVED and q.project_id == p.id
    assert (p.name, p.client_id, p.price_cents, p.style, p.size, p.body_region_id) == ("Leão realista", c.id, 120000, "Realismo", "30 cm", region.id)
    assert p.status == ProjectStatus.APPROVED and "Com coroa" in p.description and p.notes == "obs"


def test_approve_without_project_then_create_later_is_idempotent(auth_client):
    c = mk_client(); q = mk_quote(c, S.WAITING)
    post(auth_client, q, "aprovar"); db.session.refresh(q)
    assert q.status == S.APPROVED and Project.query.count() == 0
    post(auth_client, q, "criar-projeto"); post(auth_client, q, "criar-projeto")
    assert Project.query.count() == 1                       # nunca duplica


def test_cannot_create_project_before_approval(auth_client):
    c = mk_client(); q = mk_quote(c, S.SENT)
    post(auth_client, q, "criar-projeto")
    assert Project.query.count() == 0


def test_cannot_approve_draft_or_rejected(auth_client):
    c = mk_client()
    for st in (S.DRAFT, S.REJECTED, S.EXPIRED):
        q = mk_quote(c, st); post(auth_client, q, "aprovar"); db.session.refresh(q); assert q.status == st


def test_archived_client_blocks_project_creation_and_rolls_back_approval(auth_client):
    c = mk_client(); q = mk_quote(c, S.SENT)
    c.archived_at = datetime(2026, 1, 1); db.session.commit()
    post(auth_client, q, "aprovar", create_project="1"); db.session.expire_all()
    assert Project.query.count() == 0 and Quote.query.one().status == S.SENT     # nada pela metade


def test_quote_with_project_is_locked(auth_client):
    c = mk_client(); q = mk_quote(c, S.SENT); post(auth_client, q, "aprovar", create_project="1")
    assert "não pode mais ser editado" in auth_client.get(f"/orcamentos/{q.id}/editar", follow_redirects=True).get_data(as_text=True)
    assert auth_client.post(f"/orcamentos/{q.id}/editar", data=form(c, description="Mudou")).status_code == 302
    post(auth_client, q, "status", status="rascunho"); post(auth_client, q, "excluir")
    db.session.refresh(q)
    assert q.description == "Floral no antebraço" and q.status == S.APPROVED and Quote.query.count() == 1
    html = auth_client.get(f"/orcamentos/{q.id}").get_data(as_text=True)
    assert "Ver projeto criado" in html and "Excluir orçamento" not in html


def test_delete_requires_post_and_confirmation(auth_client):
    c = mk_client(); q = mk_quote(c)
    assert auth_client.get(f"/orcamentos/{q.id}/excluir").status_code == 405
    assert "data-confirm=" in auth_client.get(f"/orcamentos/{q.id}").get_data(as_text=True)
    assert post(auth_client, q, "excluir").status_code == 302 and Quote.query.count() == 0
    assert ActivityLog.query.filter_by(action="deleted", entity_type="quote").count() == 1


def test_detail_shows_actions_for_each_status(auth_client):
    c = mk_client()
    expect = {S.DRAFT: "Marcar como enviado", S.SENT: "Aprovar e criar projeto", S.WAITING: "Recusado pelo cliente",
              S.APPROVED: "Criar projeto", S.REJECTED: "Reabrir como rascunho", S.EXPIRED: "Reabrir como rascunho"}
    for st, text in expect.items():
        q = mk_quote(c, st); assert text in auth_client.get(f"/orcamentos/{q.id}").get_data(as_text=True), st


# ---------- Expiração ----------
def test_overdue_open_quotes_expire_but_others_do_not(app, auth_client):
    c = mk_client(); past = today_local() - timedelta(days=1)
    sent, wait, draft, appr, nodate = (mk_quote(c, S.SENT, valid=past), mk_quote(c, S.WAITING, valid=past),
                                       mk_quote(c, S.DRAFT, valid=past), mk_quote(c, S.APPROVED, valid=past),
                                       mk_quote(c, S.SENT))
    nodate.valid_until = None; db.session.commit()
    assert svc.expire_overdue(force=True) == 2
    db.session.expire_all()
    assert [q.status for q in (sent, wait, draft, appr, nodate)] == [S.EXPIRED, S.EXPIRED, S.DRAFT, S.APPROVED, S.SENT]
    assert ActivityLog.query.filter(ActivityLog.description.like("%expirou%")).count() == 2


def test_expiry_is_throttled(app, auth_client):
    c = mk_client(); svc.expire_overdue(force=True)
    q = mk_quote(c, S.SENT, valid=today_local() - timedelta(days=1))
    assert svc.expire_overdue() == 0                          # dentro de 1 hora: não roda
    assert svc.expire_overdue(force=True) == 1


def test_expiry_runs_on_first_authenticated_request(auth_client):
    c = mk_client(); q = mk_quote(c, S.SENT, valid=today_local() - timedelta(days=1))
    auth_client.get("/")
    db.session.refresh(q); assert q.status == S.EXPIRED


# ---------- Mensagem de WhatsApp ----------
def test_whatsapp_text_content(auth_client):
    c = mk_client("Marina Lopes"); region = BodyRegion.query.filter_by(slug="antebraco").one()
    q = mk_quote(c, style="Fine line", size="15 cm", body_region_id=region.id, notes="SEGREDO-INTERNO",
                 valid=datetime(2026, 11, 30).date())
    html = auth_client.get(f"/orcamentos/{q.id}").get_data(as_text=True)
    text = svc.whatsapp_text(q)
    assert text.startswith("Olá, Marina! Segue o orçamento da sua tatuagem no Agatha Souza Tattoo Studio:")
    for line in ("• Projeto: Floral no antebraço", "• Estilo: Fine line", "• Região: Antebraço", "• Tamanho: 15 cm",
                 "• Valor: R$ 1.200,00", "• Válido até: 30/11/2026"):
        assert line in text
    assert "SEGREDO-INTERNO" not in text and "data-copy-target=\"wa-text\"" in html
    assert "SEGREDO-INTERNO" in html                     # aparece só como observação interna da página


def test_whatsapp_text_omits_empty_fields(app):
    c = mk_client("Ana"); q = Quote(client_id=c.id, description="Rosa", price_cents=5000)
    db.session.add(q); db.session.commit()
    text = svc.whatsapp_text(q)
    assert "Estilo" not in text and "Região" not in text and "Válido" not in text and "R$ 50,00" in text


def test_client_tab_links_to_quotes(auth_client):
    c = mk_client(); q = mk_quote(c)
    html = auth_client.get(f"/clientes/{c.id}?aba=orcamentos").get_data(as_text=True)
    assert f'href="/orcamentos/{q.id}"' in html and f"/orcamentos/novo?cliente={c.id}" in html
