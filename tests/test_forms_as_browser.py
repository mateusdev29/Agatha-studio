"""Formulários testados COMO O NAVEGADOR: só os campos que a tela exibe, com os valores já preenchidos.

Por que existe: um formulário podia exigir um campo que a tela não mostra (ex.: cliente na despesa). O navegador nunca o
enviava, a validação falhava em silêncio e nada era salvo, mas os testes passavam porque postavam TODOS os campos.
"""
from datetime import datetime, time, timedelta
from html.parser import HTMLParser

import pytest
from flask import render_template_string
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired

from app.extensions import db
from app.models import (AnamnesisTemplate, Appointment, Category, Client, Evaluation, FinancialTransaction as T,
                        InventoryItem, Project, ProjectSession, Quote, Service)
from app.models.enums import AppointmentStatus, CategoryKind, QuoteStatus, TransactionType
from app.utils.dates import today_local


class _Forms(HTMLParser):
    """Extrai <form> com seus campos, como um navegador montaria o envio."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms, self._form, self._select, self._textarea = [], None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._form = {"action": a.get("action") or "", "method": (a.get("method") or "get").lower(), "fields": []}
            self.forms.append(self._form)
        elif self._form is None or "disabled" in a:
            return
        elif tag == "input":
            t, name = (a.get("type") or "text").lower(), a.get("name")
            if not name or t in ("submit", "button", "file", "image", "reset"):
                return
            if t in ("checkbox", "radio") and "checked" not in a:
                return
            self._form["fields"].append([name, a.get("value", "on" if t in ("checkbox", "radio") else "")])
        elif tag == "select" and a.get("name"):
            self._select = {"name": a["name"], "first": None, "chosen": None}
        elif tag == "option" and self._select is not None and "disabled" not in a:
            value = a.get("value", "")
            if self._select["first"] is None:
                self._select["first"] = value
            if "selected" in a:
                self._select["chosen"] = value
        elif tag == "textarea" and a.get("name"):
            self._textarea = [a["name"], ""]

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == "select" and self._select is not None:
            s, self._select = self._select, None
            self._form["fields"].append([s["name"], s["chosen"] if s["chosen"] is not None else (s["first"] or "")])
        elif tag == "textarea" and self._textarea is not None:
            f, self._textarea = self._textarea, None
            self._form["fields"].append([f[0], f[1].lstrip("\n")])
        elif tag == "form":
            self._form = None


def submit(client, url, overrides=None, action_contains=None):
    """GET da tela e POST só do que ela exibe (+ valores que a pessoa digitou)."""
    page = client.get(url)
    assert page.status_code == 200, f"GET {url} -> {page.status_code}"
    p = _Forms(); p.feed(page.get_data(as_text=True))
    forms = [f for f in p.forms if f["method"] == "post" and not f["action"].endswith("/logout")
             and (action_contains is None or action_contains in (f["action"] or url))]
    assert forms, f"nenhum formulário POST em {url}"
    form = forms[0]
    data = {}
    for name, value in form["fields"]:
        data.setdefault(name, []).append(value)
    for name, value in (overrides or {}).items():
        data[name] = value if isinstance(value, list) else [value]
    return client.post(form["action"] or url, data={k: (v if len(v) > 1 else v[0]) for k, v in data.items()}), form


def rendered(form):
    return {n for n, _ in form["fields"]}


# ---------------------------------------------------------------- o bug que motivou o arquivo
def test_expense_can_be_created_with_only_the_fields_the_screen_shows(auth_client):
    cat = Category.query.filter_by(kind=CategoryKind.EXPENSE, name="Materiais").one()
    r, form = submit(auth_client, "/financeiro/despesas/nova", {"description": "Agulhas e cartuchos", "amount_cents": "280,00", "category_id": str(cat.id), "supplier": "Tattoo Supply"})
    assert "client_id" not in rendered(form) and "project_id" not in rendered(form)            # a tela de despesa realmente não os exibe
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    t = T.query.one()
    assert (t.type, t.description, t.amount_cents, t.supplier, t.category_id, t.client_id, t.project_id) == (TransactionType.EXPENSE, "Agulhas e cartuchos", 28000, "Tattoo Supply", cat.id, None, None)
    assert "Agulhas e cartuchos" in auth_client.get("/financeiro/?aba=despesas").get_data(as_text=True)
    assert "R$ 280,00" in auth_client.get("/financeiro/").get_data(as_text=True)


def test_expense_can_be_edited_with_only_the_fields_the_screen_shows(auth_client):
    t = T(type=TransactionType.EXPENSE, description="Aluguel", amount_cents=150000, date=today_local(), supplier="Imobiliária"); db.session.add(t); db.session.commit()
    r, form = submit(auth_client, f"/financeiro/{t.id}/editar", {"amount_cents": "1.600,00"})
    assert r.status_code == 302 and "client_id" not in rendered(form)
    db.session.refresh(t); assert (t.amount_cents, t.supplier, t.client_id) == (160000, "Imobiliária", None)


def test_invalid_expense_shows_a_visible_error_and_saves_nothing(auth_client):
    r, _ = submit(auth_client, "/financeiro/despesas/nova", {"description": "Sem valor", "amount_cents": "0"})
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and 'role="alert"' in html and "Não foi possível salvar" in html and "maior que zero" in html and T.query.count() == 0


def test_errors_on_fields_the_screen_does_not_render_are_still_shown(app):
    class F(FlaskForm):
        visivel = StringField("Nome visível", validators=[DataRequired(message="Obrigatório.")])
        escondido = StringField("Campo escondido", validators=[DataRequired(message="Faltou aqui.")])
    with app.test_request_context(method="POST", data={"visivel": "ok"}):
        f = F(); f.validate()
        html = render_template_string('{% from "components/_forms.html" import form_errors %}{{ form_errors(f) }}', f=f)
    assert "Não foi possível salvar" in html and "Campo escondido: Faltou aqui." in html and "role=\"alert\"" in html


# ---------------------------------------------------------------- todos os formulários, criar e editar
@pytest.fixture()
def world(app):
    c = Client(name="Marina Lopes", source="Instagram"); db.session.add(c); db.session.flush()
    p = Project(client_id=c.id, name="Floral", price_cents=100000); db.session.add(p); db.session.flush()
    q = Quote(client_id=c.id, description="Rosa", price_cents=50000, valid_until=today_local() + timedelta(days=9), status=QuoteStatus.DRAFT)
    a = Appointment(client_id=c.id, starts_at=datetime.combine(today_local() + timedelta(days=9), time(10)), duration_minutes=60, status=AppointmentStatus.WAITING, service="Sessão", price_cents=60000, deposit_cents=10000)
    s = ProjectSession(project_id=p.id, scheduled_at=datetime.combine(today_local() + timedelta(days=9), time(10)), duration_minutes=120, price_cents=30000)
    item = InventoryItem(name="Agulha", quantity=5, min_quantity=2, unit="un")
    inc = T(type=TransactionType.INCOME, description="Receita", amount_cents=1000, date=today_local(), client_id=c.id)
    exp = T(type=TransactionType.EXPENSE, description="Despesa", amount_cents=1000, date=today_local())
    svc_ = Service(name="Serviço de teste"); cat_f = Category(kind=CategoryKind.INCOME, name="Extra"); cat_e = Category(kind=CategoryKind.INVENTORY, name="Cremes")
    qs = AnamnesisTemplate(label="Pergunta extra?", position=99)
    db.session.add_all([q, a, s, item, inc, exp, svc_, cat_f, cat_e, qs]); db.session.flush()
    ev = Evaluation(client_id=c.id, score=9, evaluated_on=today_local()); db.session.add(ev); db.session.commit()
    return dict(c=c, p=p, q=q, a=a, s=s, item=item, inc=inc, exp=exp, svc=svc_, cat_f=cat_f, cat_e=cat_e, qs=qs, ev=ev)


CREATE = [  # (url, o que a pessoa digita, trecho da action)
    ("/clientes/novo", {"name": "Novo Cliente"}, None),
    ("/projetos/novo", {"name": "Novo Projeto"}, None),
    ("/orcamentos/novo", {"description": "Leão", "price_cents": "800,00"}, None),
    ("/agenda/novo", {"time": "14:00"}, None),
    ("/financeiro/receitas/nova", {"description": "Entrada", "amount_cents": "10,00"}, None),
    ("/financeiro/despesas/nova", {"description": "Saída", "amount_cents": "10,00"}, None),
    ("/satisfacao/nova", {"score": "8"}, None),
    ("/estoque/novo", {"name": "Tinta nova"}, None),
    ("/configuracoes/servicos", {"name": "Flash day", "default_price_cents": "10"}, "servicos"),
    ("/configuracoes/categorias/financeiras", {"name": "Workshop"}, "categorias"),
    ("/configuracoes/categorias/estoque", {"name": "Luvas"}, "categorias"),
    ("/anamnese/perguntas", {"label": "Usa óculos?"}, "perguntas"),
    ("/configuracoes/perfil", {}, "perfil"),
    ("/configuracoes/estudio", {}, None),
    ("/configuracoes/preferencias", {}, None),
]


@pytest.mark.parametrize("url,typed,action", CREATE, ids=[c[0] for c in CREATE])
def test_every_create_form_saves_when_posted_like_a_browser(auth_client, world, url, typed, action):
    r, form = submit(auth_client, url, typed, action)
    assert r.status_code in (302, 303), f"{url}: não salvou. Campos enviados: {sorted(rendered(form))}\n{r.get_data(as_text=True)[:600]}"


def _edit_cases(w):
    return [
        (f"/clientes/{w['c'].id}/editar", None), (f"/projetos/{w['p'].id}/editar", None), (f"/orcamentos/{w['q'].id}/editar", None),
        (f"/agenda/{w['a'].id}/editar", None), (f"/projetos/{w['p'].id}/sessoes/{w['s'].id}/editar", None),
        (f"/financeiro/{w['inc'].id}/editar", None), (f"/financeiro/{w['exp'].id}/editar", None), (f"/estoque/{w['item'].id}/editar", None),
        (f"/configuracoes/servicos/{w['svc'].id}/editar", None), (f"/configuracoes/categorias/{w['cat_f'].id}/editar", None),
        (f"/configuracoes/categorias/{w['cat_e'].id}/editar", None), (f"/anamnese/perguntas/{w['qs'].id}/editar", None), (f"/satisfacao/{w['ev'].id}/editar", None),
    ]


def test_every_edit_form_saves_unchanged_when_posted_like_a_browser(auth_client, world):
    for url, action in _edit_cases(world):
        r, form = submit(auth_client, url, None, action)
        assert r.status_code in (302, 303), f"{url}: salvar sem alterar falhou. Campos: {sorted(rendered(form))}\n{r.get_data(as_text=True)[:500]}"


def test_stock_movement_and_deposit_forms_work_as_rendered(auth_client, world):
    r, _ = submit(auth_client, f"/estoque/{world['item'].id}", {"type": "entrada", "quantity": "3"}, "movimentar")
    assert r.status_code == 302 and db.session.get(InventoryItem, world["item"].id).quantity == 8
    r, _ = submit(auth_client, f"/agenda/{world['a'].id}", {"payment_method": "pix"}, "sinal")
    assert r.status_code == 302 and T.query.filter_by(is_deposit=True).count() == 1
