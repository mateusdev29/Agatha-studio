from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import (ActivityLog, Appointment, Category, Client, FinancialTransaction as T, InventoryItem, InventoryMovement,
                        Project, Service, StudioSetting, User)
from app.models.enums import CategoryKind, PaymentMethod, TransactionStatus as TS, TransactionType as TT
from app.utils.dates import today_local
from app.utils.periods import parse_period


def mk_client(name="Marina Lopes"):
    c = Client(name=name); db.session.add(c); db.session.commit(); return c


def cat(kind, name):
    return Category.query.filter_by(kind=kind, name=name).one()


def tx(kind=TT.INCOME, cents=10000, days=0, status=TS.PAID, **kw):
    t = T(type=kind, description=kw.pop("description", "Lançamento"), amount_cents=cents, date=today_local() + timedelta(days=days), status=status, **kw)
    db.session.add(t); db.session.commit(); return t


def fform(**over):
    d = {"description": "Sinal Floral", "category_id": 0, "amount_cents": "150,00", "date": today_local().isoformat(),
         "payment_method": "pix", "status": "pago", "client_id": 0, "project_id": 0, "supplier": "", "notes": ""}
    d.update(over); return d


# ================= Períodos =================
def test_period_presets_and_fallbacks(app):
    t = today_local()
    p = parse_period({"periodo": "mes"}); assert p.start == t.replace(day=1) and p.start <= t <= p.end and p.end.month == t.month
    prev = parse_period({"periodo": "mes_anterior"}); assert prev.end == t.replace(day=1) - timedelta(days=1) and prev.start.day == 1
    assert parse_period({"periodo": "30d"}).start == t - timedelta(days=29)
    assert parse_period({"periodo": "ano"}).start == date(t.year, 1, 1) and parse_period({"periodo": "tudo"}).start.year == 2000
    assert parse_period({"periodo": "lixo"}).key == "mes" and parse_period({}).key == "mes"
    c = parse_period({"de": "2026-01-01", "ate": "2026-01-31"}); assert (c.key, c.start, c.end) == ("custom", date(2026, 1, 1), date(2026, 1, 31)) and c.args == {"de": "2026-01-01", "ate": "2026-01-31"}
    for bad in ({"de": "2026-02-01", "ate": "2026-01-01"}, {"de": "x", "ate": "y"}, {"de": "2026-01-01"}, {"de": "1990-01-01", "ate": "2026-01-01"}, {"de": "2000-01-01", "ate": "2100-12-31"}):
        assert parse_period(bad).key == "mes", bad


# ================= Financeiro =================
@pytest.mark.parametrize("path", ["/financeiro/", "/financeiro/receitas/nova", "/financeiro/1/editar"])
def test_finance_requires_login(client, path):
    assert client.get(path).status_code == 302


def test_create_income_and_expense(auth_client):
    c = mk_client(); p = Project(client_id=c.id, name="Floral"); db.session.add(p); db.session.commit()
    r = auth_client.post("/financeiro/receitas/nova", data=fform(category_id=cat(CategoryKind.INCOME, "Tatuagem").id, project_id=p.id))
    assert r.status_code == 302
    t = T.query.one()
    assert (t.type, t.amount_cents, t.payment_method, t.status, t.project_id, t.client_id) == (TT.INCOME, 15000, PaymentMethod.PIX, TS.PAID, p.id, c.id)   # cliente deduzido do projeto
    auth_client.post("/financeiro/despesas/nova", data=fform(description="Agulhas", supplier="Tattoo Supply", client_id=c.id, project_id=p.id, category_id=cat(CategoryKind.EXPENSE, "Materiais").id))
    e = T.query.filter_by(type=TT.EXPENSE).one()
    assert e.supplier == "Tattoo Supply" and e.client_id is None and e.project_id is None        # despesa não guarda cliente/projeto
    assert ActivityLog.query.filter_by(entity_type="transaction").count() == 2


@pytest.mark.parametrize("over,msg", [
    ({"description": ""}, "Informe a descrição."), ({"amount_cents": "0"}, "maior que zero"), ({"amount_cents": ""}, "maior que zero"),
    ({"amount_cents": "abc"}, "Valor inválido"), ({"date": ""}, "Informe a data."), ({"date": "1999-01-01"}, "Data inválida"),
    ({"status": "xx"}, "Not a valid choice"), ({"payment_method": "boleto"}, "Not a valid choice"), ({"category_id": 9999}, "Not a valid choice"),
])
def test_finance_validation(auth_client, over, msg):
    r = auth_client.post("/financeiro/receitas/nova", data=fform(**over))
    assert r.status_code == 400 and msg in r.get_data(as_text=True) and T.query.count() == 0


def test_category_must_match_kind(auth_client):
    r = auth_client.post("/financeiro/receitas/nova", data=fform(category_id=cat(CategoryKind.EXPENSE, "Materiais").id))
    assert r.status_code == 400 and T.query.count() == 0


def test_project_must_belong_to_client(auth_client):
    a, b = mk_client("A"), mk_client("B"); p = Project(client_id=b.id, name="Do B"); db.session.add(p); db.session.commit()
    assert auth_client.post("/financeiro/receitas/nova", data=fform(client_id=a.id, project_id=p.id)).status_code == 400


def test_unknown_kind_is_404(auth_client):
    assert auth_client.get("/financeiro/lixo/nova").status_code == 404


def test_edit_pay_delete(auth_client):
    t = tx(status=TS.PENDING, description="Restante")
    assert 'value="Restante"' in auth_client.get(f"/financeiro/{t.id}/editar").get_data(as_text=True)
    assert auth_client.post(f"/financeiro/{t.id}/editar", data=fform(description="Restante 2", status="pendente")).status_code == 302
    db.session.refresh(t); assert t.description == "Restante 2" and t.status == TS.PENDING
    assert auth_client.get(f"/financeiro/{t.id}/pagar").status_code == 405
    auth_client.post(f"/financeiro/{t.id}/pagar"); db.session.refresh(t); assert t.status == TS.PAID
    assert "Só lançamentos pendentes" in auth_client.post(f"/financeiro/{t.id}/pagar", follow_redirects=True).get_data(as_text=True)
    assert "data-confirm=" in auth_client.get(f"/financeiro/{t.id}/editar").get_data(as_text=True)
    auth_client.post(f"/financeiro/{t.id}/excluir"); assert T.query.count() == 0
    assert ActivityLog.query.filter_by(action="deleted", entity_type="transaction").count() == 1


def test_pay_redirect_ignores_external_referrer(auth_client):
    t = tx(status=TS.PENDING)
    r = auth_client.post(f"/financeiro/{t.id}/pagar", headers={"Referer": "https://evil.example.com/financeiro/"})
    assert "evil.example.com" not in r.headers["Location"]


def test_summary_counts_only_paid_and_respects_period(auth_client):
    tx(TT.INCOME, 100000); tx(TT.INCOME, 50000, status=TS.PENDING); tx(TT.INCOME, 70000, days=-400)
    tx(TT.EXPENSE, 30000); tx(TT.EXPENSE, 20000, status=TS.PENDING); tx(TT.EXPENSE, 9000, status=TS.CANCELED)
    html = auth_client.get("/financeiro/").get_data(as_text=True)
    for text in ("R$ 1.000,00", "R$ 300,00", "R$ 700,00", "R$ 500,00", "A pagar: R$ 200,00"):
        assert text in html, text
    assert "R$ 700,00" in auth_client.get("/financeiro/?periodo=mes").get_data(as_text=True)
    assert "R$ 1.700,00" in auth_client.get("/financeiro/?periodo=tudo").get_data(as_text=True)      # entra o de 400 dias atrás


def test_tabs_filters_and_pagination(auth_client):
    c = mk_client("Marina"); tx(TT.INCOME, 1000, description="Entrada A", client_id=c.id); tx(TT.INCOME, 1000, description="Entrada B"); tx(TT.EXPENSE, 1000, description="Saída C", supplier="Forn")
    get = lambda **q: auth_client.get("/financeiro/", query_string=q).get_data(as_text=True)
    assert "Entrada A" in get(aba="receitas") and "Saída C" not in get(aba="receitas")
    assert "Saída C" in get(aba="despesas") and "Entrada A" not in get(aba="despesas")
    assert "Entrada A" in get(aba="pagamentos") and "Entrada B" not in get(aba="pagamentos")            # só receitas com cliente
    assert "Saída C" in get(q="forn") and "Entrada A" not in get(q="forn")
    assert "Entrada A" in get(q="marina") and get(aba="lixo").count("Lançamentos") >= 1
    for i in range(25): tx(description=f"P{i}")
    assert 'aria-label="Paginação"' in get()


def test_categories_tab_breakdown(auth_client):
    tx(TT.INCOME, 40000, category_id=cat(CategoryKind.INCOME, "Tatuagem").id); tx(TT.EXPENSE, 9000, category_id=cat(CategoryKind.EXPENSE, "Materiais").id)
    html = auth_client.get("/financeiro/?aba=categorias").get_data(as_text=True)
    assert "Tatuagem" in html and "R$ 400,00" in html and "Materiais" in html


def test_finance_xss(auth_client):
    tx(description="<script>alert(1)</script>", notes="<b>x</b>")
    for path in ("/financeiro/", "/financeiro/1/editar"):
        assert "<script>alert(1)</script>" not in auth_client.get(path).get_data(as_text=True)


# ================= Estoque =================
def sform(**over):
    d = {"name": "Agulha 3RL", "category_id": 0, "quantity": 10, "unit": "un", "min_quantity": 5, "cost_cents": "4,50", "supplier": "Tattoo Supply", "expires_on": "", "notes": ""}
    d.update(over); return d


def mk_item(qty=10, mn=5, **kw):
    i = InventoryItem(name=kw.pop("name", "Tinta"), quantity=qty, min_quantity=mn, **kw); db.session.add(i); db.session.commit(); return i


def move(c, item, t, q, reason=""):
    return c.post(f"/estoque/{item.id}/movimentar", data={"type": t, "quantity": q, "reason": reason})


def test_stock_requires_login(client):
    assert client.get("/estoque/").status_code == 302 and client.post("/estoque/1/movimentar").status_code == 302


def test_create_item_records_initial_balance(auth_client):
    assert auth_client.post("/estoque/novo", data=sform()).status_code == 302
    i = InventoryItem.query.one(); m = InventoryMovement.query.one()
    assert (i.quantity, i.cost_cents, m.delta, m.balance_after, m.reason) == (10, 450, 10, 10, "Saldo inicial")
    auth_client.post("/estoque/novo", data=sform(name="Sem saldo", quantity=0))
    assert InventoryMovement.query.count() == 1                      # saldo zero não gera movimentação


@pytest.mark.parametrize("over,msg", [({"name": ""}, "Informe o produto."), ({"quantity": -1}, "Quantidade inválida"), ({"unit": ""}, "Informe a unidade."),
                                      ({"min_quantity": -3}, "Valor inválido"), ({"cost_cents": "x"}, "Valor inválido"), ({"expires_on": "2101-01-01"}, "Data inválida")])
def test_item_validation(auth_client, over, msg):
    r = auth_client.post("/estoque/novo", data=sform(**over))
    assert r.status_code == 400 and msg in r.get_data(as_text=True) and InventoryItem.query.count() == 0


def test_movements_update_balance_and_history(auth_client):
    i = mk_item(10)
    move(auth_client, i, "entrada", 5, "Compra"); move(auth_client, i, "saida", 3, "Uso"); move(auth_client, i, "ajuste", 20, "Inventário")
    db.session.refresh(i)
    rows = InventoryMovement.query.order_by(InventoryMovement.id).all()
    assert i.quantity == 20 and [(m.type.value, m.delta, m.balance_after) for m in rows] == [("entrada", 5, 15), ("saida", -3, 12), ("ajuste", 8, 20)]
    assert all(m.user_id for m in rows)


def test_stock_never_goes_negative(auth_client):
    i = mk_item(2)
    r = auth_client.post(f"/estoque/{i.id}/movimentar", data={"type": "saida", "quantity": 3}, follow_redirects=True)
    assert "Saldo insuficiente" in r.get_data(as_text=True)
    db.session.refresh(i); assert i.quantity == 2 and InventoryMovement.query.count() == 0


@pytest.mark.parametrize("t,q", [("entrada", 0), ("saida", 0), ("entrada", -1), ("ajuste", -1), ("entrada", ""), ("lixo", 1)])
def test_invalid_movements_change_nothing(auth_client, t, q):
    i = mk_item(5); move(auth_client, i, t, q)
    db.session.refresh(i); assert i.quantity == 5 and InventoryMovement.query.count() == 0


def test_adjustment_can_zero_the_balance(auth_client):
    i = mk_item(5); move(auth_client, i, "ajuste", 0); db.session.refresh(i); assert i.quantity == 0


def test_archived_item_cannot_move_and_can_restore(auth_client):
    i = mk_item(5); auth_client.post(f"/estoque/{i.id}/arquivar"); db.session.refresh(i); assert not i.is_active
    move(auth_client, i, "entrada", 1); db.session.refresh(i); assert i.quantity == 5
    assert f"/estoque/{i.id}" not in auth_client.get("/estoque/").get_data(as_text=True)
    assert f"/estoque/{i.id}" in auth_client.get("/estoque/?status=arquivados").get_data(as_text=True)
    auth_client.post(f"/estoque/{i.id}/restaurar"); db.session.refresh(i); assert i.is_active


def test_low_stock_banner_filter_and_notification(auth_client):
    mk_item(2, 5, name="Baixo"); mk_item(50, 5, name="Cheio")
    html = auth_client.get("/estoque/").get_data(as_text=True)
    assert "1 produto com estoque baixo" in html
    low = auth_client.get("/estoque/?baixo=1").get_data(as_text=True)
    assert "Baixo" in low and "Cheio" not in low
    assert "Estoque baixo: Baixo" in auth_client.get("/").get_data(as_text=True)


def test_stock_search_category_and_movements_tab(auth_client):
    a = mk_item(5, name="Agulha", category_id=cat(CategoryKind.INVENTORY, "Agulhas").id); t = mk_item(5, name="Tinta", category_id=cat(CategoryKind.INVENTORY, "Tintas").id)
    get = lambda **q: auth_client.get("/estoque/", query_string=q).get_data(as_text=True)
    link = lambda i: f'href="/estoque/{i.id}"'                       # o link do item é inequívoco (o nome também aparece no filtro de categorias)
    assert link(a) in get(q="agu") and link(t) not in get(q="agu")
    tintas = get(categoria=cat(CategoryKind.INVENTORY, "Tintas").id)
    assert link(t) in tintas and link(a) not in tintas
    move(auth_client, a, "entrada", 3, "Compra de teste")
    assert "Compra de teste" in get(aba="movimentacoes")
    assert "Compra de teste" in auth_client.get(f"/estoque/{a.id}").get_data(as_text=True)


def test_edit_item_cannot_change_quantity(auth_client):
    i = mk_item(7); assert 'name="quantity"' not in auth_client.get(f"/estoque/{i.id}/editar").get_data(as_text=True)
    auth_client.post(f"/estoque/{i.id}/editar", data=sform(name="Novo nome", quantity=999)); db.session.refresh(i)
    assert i.name == "Novo nome" and i.quantity == 7


def test_stock_xss_and_move_requires_post(auth_client):
    i = mk_item(1, name="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in auth_client.get("/estoque/").get_data(as_text=True) + auth_client.get(f"/estoque/{i.id}").get_data(as_text=True)
    assert auth_client.get(f"/estoque/{i.id}/movimentar").status_code == 405


# ================= Configurações =================
def test_settings_requires_login(client):
    for p in ("/configuracoes/perfil", "/configuracoes/estudio", "/configuracoes/servicos", "/configuracoes/categorias/estoque"):
        assert client.get(p).status_code == 302


def test_profile_update_and_unique_email(auth_client):
    db.session.add(User(name="Outra", email="outra@example.com", password_hash="x")); db.session.commit()
    assert auth_client.post("/configuracoes/perfil", data={"name": "Agatha S.", "email": "AGATHA@Example.com"}).status_code == 302
    u = User.query.filter_by(name="Agatha S.").one(); assert u.email == "agatha@example.com"
    r = auth_client.post("/configuracoes/perfil", data={"name": "X", "email": "outra@example.com"})
    assert r.status_code == 400 and "já está em uso" in r.get_data(as_text=True)


def test_password_change_rules(app, auth_client, client):
    from tests.conftest import TEST_PASSWORD
    post = lambda **d: auth_client.post("/configuracoes/senha", data=d)
    assert "Senha atual incorreta" in post(current="errada", new="nova-senha-forte", confirm="nova-senha-forte").get_data(as_text=True)
    assert "10 a 128" in post(current=TEST_PASSWORD, new="curta", confirm="curta").get_data(as_text=True)
    assert "não coincidem" in post(current=TEST_PASSWORD, new="nova-senha-forte", confirm="outra-coisa").get_data(as_text=True)
    assert User.query.first().check_password(TEST_PASSWORD)
    assert post(current=TEST_PASSWORD, new="nova-senha-forte", confirm="nova-senha-forte").status_code == 302
    u = User.query.first(); assert u.check_password("nova-senha-forte") and not u.check_password(TEST_PASSWORD) and "nova-senha-forte" not in u.password_hash
    assert not any("nova-senha" in (a.description or "") for a in ActivityLog.query.all())


def test_studio_name_is_used_in_whatsapp_text(auth_client):
    from app.models import Quote
    c = mk_client("Ana Souza"); q = Quote(client_id=c.id, description="Rosa", price_cents=5000); db.session.add(q); db.session.commit()
    assert "Agatha Souza Tattoo Studio" in auth_client.get(f"/orcamentos/{q.id}").get_data(as_text=True)
    assert auth_client.post("/configuracoes/estudio", data={"studio_name": "Studio Nova", "studio_phone": "", "studio_instagram": "", "studio_address": ""}).status_code == 302
    assert "no Studio Nova:" in auth_client.get(f"/orcamentos/{q.id}").get_data(as_text=True)
    assert 'value="Studio Nova"' in auth_client.get("/configuracoes/estudio").get_data(as_text=True)


def test_preferences_drive_real_defaults(auth_client):
    c = mk_client()
    assert auth_client.post("/configuracoes/preferencias", data={"pref_quote_validity_days": 30, "pref_default_duration": 90}).status_code == 302
    assert (today_local() + timedelta(days=30)).isoformat() in auth_client.get(f"/orcamentos/novo?cliente={c.id}").get_data(as_text=True)
    assert 'value="90"' in auth_client.get("/agenda/novo").get_data(as_text=True)
    for bad in ({"pref_quote_validity_days": 0, "pref_default_duration": 90}, {"pref_quote_validity_days": 30, "pref_default_duration": 5}, {"pref_quote_validity_days": 999, "pref_default_duration": 90}):
        assert auth_client.post("/configuracoes/preferencias", data=bad).status_code == 400


def test_services_crud_and_unique_name(auth_client):
    assert auth_client.post("/configuracoes/servicos", data={"name": "Flash day", "default_duration_minutes": 60, "default_price_cents": "150,00", "is_active": "y"}).status_code == 302
    s = Service.query.filter_by(name="Flash day").one(); assert (s.default_duration_minutes, s.default_price_cents, s.is_active) == (60, 15000, True)
    dup = auth_client.post("/configuracoes/servicos", data={"name": "FLASH DAY", "default_duration_minutes": 60, "default_price_cents": "0"})
    assert dup.status_code == 400 and "Já existe" in dup.get_data(as_text=True)
    auth_client.post(f"/configuracoes/servicos/{s.id}/editar", data={"name": "Flash day", "default_duration_minutes": 45, "default_price_cents": "100"})   # sem is_active = desativa
    db.session.refresh(s); assert (s.default_duration_minutes, s.is_active) == (45, False)
    assert "Flash day" not in auth_client.get("/agenda/novo").get_data(as_text=True)          # inativo some das sugestões


def test_category_management_affects_forms(auth_client):
    assert auth_client.post("/configuracoes/categorias/financeiras", data={"name": "Workshop", "kind": "receita", "is_active": "y"}).status_code == 302
    c = Category.query.filter_by(name="Workshop").one(); assert c.kind == CategoryKind.INCOME
    assert "Workshop" in auth_client.get("/financeiro/receitas/nova").get_data(as_text=True)
    assert "Workshop" not in auth_client.get("/financeiro/despesas/nova").get_data(as_text=True)
    assert auth_client.post("/configuracoes/categorias/financeiras", data={"name": "workshop", "kind": "receita"}).status_code == 400
    assert auth_client.post("/configuracoes/categorias/financeiras", data={"name": "Workshop", "kind": "despesa", "is_active": "y"}).status_code == 302   # mesmo nome em outro tipo é permitido
    auth_client.post(f"/configuracoes/categorias/{c.id}/editar", data={"name": "Workshop"})            # desativa
    assert "Workshop" not in auth_client.get("/financeiro/receitas/nova").get_data(as_text=True)
    assert auth_client.post("/configuracoes/categorias/estoque", data={"name": "Cremes", "is_active": "y"}).status_code == 302
    assert Category.query.filter_by(name="Cremes").one().kind == CategoryKind.INVENTORY
    assert auth_client.get("/configuracoes/categorias/lixo").status_code == 404


def test_deactivated_category_stays_selectable_on_existing_transaction(auth_client):
    c = cat(CategoryKind.INCOME, "Retoque"); t = tx(category_id=c.id); c.is_active = False; db.session.commit()
    assert f'<option selected value="{c.id}">' in auth_client.get(f"/financeiro/{t.id}/editar").get_data(as_text=True)
