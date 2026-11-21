import json
import re
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import (ActivityLog, AnamnesisResponse, AnamnesisTemplate as Q, Appointment, BodyRegion, Client, Evaluation,
                        FinancialTransaction as T, Project)
from app.models.enums import AppointmentStatus as A, FieldType as FT, ProjectStatus as P, TransactionStatus as TS, TransactionType as TT
from app.services import analytics_service as an
from app.utils.dates import now_local, today_local
from app.utils.periods import parse_period

SECRET = "SEGREDO-DE-SAUDE-XYZ"


def mk_client(name="Marina Lopes", **kw):
    c = Client(name=name, **kw); db.session.add(c); db.session.commit(); return c


def answers_for(c, **over):
    """Preenche todas as perguntas ativas com respostas válidas."""
    data = {"client_id": c.id, "accepted": "y", "signature_name": "Marina Lopes"}
    for q in Q.query.filter_by(is_active=True).all():
        data[f"q_{q.id}"] = (q.options[0] if q.options else SECRET)
    data.update(over); return data


# ================= Anamnese =================
def test_default_questions_are_seeded(app):
    assert Q.query.count() == 8 and Q.query.filter_by(required=True).count() == 6


def test_anamnesis_requires_login(client):
    for p in ("/anamnese/", "/anamnese/nova", "/anamnese/1", "/anamnese/perguntas"):
        assert client.get(p).status_code == 302


def test_fill_creates_immutable_snapshot(auth_client):
    c = mk_client(); r = auth_client.post("/anamnese/nova", data=answers_for(c))
    resp = AnamnesisResponse.query.one()
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/anamnese/{resp.id}")
    assert resp.accepted and resp.accepted_at and resp.signature_name == "Marina Lopes" and len(resp.answers) == 8
    assert all({"id", "label", "type", "value"} <= set(a) for a in resp.answers)
    q = Q.query.first(); q.label = "Pergunta alterada depois"; db.session.commit()                   # editar a pergunta não muda a ficha
    assert "Pergunta alterada depois" not in auth_client.get(f"/anamnese/{resp.id}").get_data(as_text=True)
    assert auth_client.post(f"/anamnese/{resp.id}", data={}).status_code == 405                     # sem edição/remoção


def test_required_accept_and_signature_are_enforced(auth_client):
    c = mk_client()
    for over, msg in [({"accepted": ""}, "aceitar o termo"), ({"signature_name": ""}, "Digite seu nome completo")]:
        r = auth_client.post("/anamnese/nova", data=answers_for(c, **over))
        assert r.status_code == 400 and msg in r.get_data(as_text=True)
    first = Q.query.filter_by(required=True).first()
    r = auth_client.post("/anamnese/nova", data=answers_for(c, **{f"q_{first.id}": ""}))
    assert r.status_code == 400 and "Resposta obrigatória." in r.get_data(as_text=True) and AnamnesisResponse.query.count() == 0


def test_answer_values_are_validated_by_type(auth_client):
    c = mk_client()
    radio = Q.query.filter_by(field_type=FT.RADIO).first()
    assert auth_client.post("/anamnese/nova", data=answers_for(c, **{f"q_{radio.id}": "Talvez"})).status_code == 400
    sel = Q(label="Sangue", field_type=FT.SELECT, options=["A", "B"], position=50); chk = Q(label="Sintomas", field_type=FT.CHECKBOX, options=["Tosse", "Febre"], position=51)
    dt = Q(label="Última vez", field_type=FT.DATE, position=52); db.session.add_all([sel, chk, dt]); db.session.commit()
    ok = answers_for(c, **{f"q_{sel.id}": "A", f"q_{chk.id}": ["Tosse", "Febre"], f"q_{dt.id}": "2026-01-15"})
    assert auth_client.post("/anamnese/nova", data={**ok, f"q_{sel.id}": "Z"}).status_code == 400
    assert auth_client.post("/anamnese/nova", data={**ok, f"q_{chk.id}": ["Tosse", "Inventado"]}).status_code == 400
    assert auth_client.post("/anamnese/nova", data={**ok, f"q_{dt.id}": "31/02/2026"}).status_code == 400
    assert auth_client.post("/anamnese/nova", data={**ok, f"q_{radio.id}": radio.options[0], f"q_{sel.id}": "A"}).status_code == 302
    html = auth_client.get(f"/anamnese/{AnamnesisResponse.query.one().id}").get_data(as_text=True)
    assert "Tosse, Febre" in html and "15/01/2026" in html


def test_inactive_questions_are_not_asked(auth_client):
    c = mk_client(); q = Q.query.first(); label = q.label; q.is_active = False; db.session.commit()
    assert label not in auth_client.get("/anamnese/nova").get_data(as_text=True)
    assert auth_client.post("/anamnese/nova", data=answers_for(c)).status_code == 302 and len(AnamnesisResponse.query.one().answers) == 7


def test_archived_client_cannot_get_form(auth_client):
    c = mk_client(archived_at=datetime(2026, 1, 1))
    assert auth_client.post("/anamnese/nova", data=answers_for(c)).status_code == 400


def test_health_answers_never_leak(auth_client):
    c = mk_client(); auth_client.post("/anamnese/nova", data=answers_for(c)); rid = AnamnesisResponse.query.one().id
    assert SECRET in auth_client.get(f"/anamnese/{rid}").get_data(as_text=True)                     # só aqui
    for path in ("/", "/dashboard/", "/satisfacao/", "/preferencias-corporais/", "/clientes/", f"/clientes/{c.id}", f"/clientes/{c.id}?aba=anamnese",
                 "/anamnese/", "/anamnese/perguntas", "/financeiro/", "/agenda/?vista=mes", "/configuracoes/perfil"):
        assert SECRET not in auth_client.get(path).get_data(as_text=True), path
    assert not any(SECRET in (a.description or "") for a in ActivityLog.query.all())               # nem no log de atividades
    assert SECRET not in json.dumps([x for x in an.projects_by_style(parse_period({"periodo": "tudo"})).values()])


def test_detail_is_not_cacheable_and_escapes(auth_client):
    c = mk_client(); auth_client.post("/anamnese/nova", data=answers_for(c, signature_name="<script>alert(1)</script>"))
    r = auth_client.get(f"/anamnese/{AnamnesisResponse.query.one().id}")
    assert r.headers["Cache-Control"] == "no-store" and "<script>alert(1)</script>" not in r.get_data(as_text=True)


def test_question_management(auth_client):
    base = {"label": "Usa óculos?", "field_type": "radio", "options_text": "Sim\nNão", "position": 99, "is_active": "y"}
    assert auth_client.post("/anamnese/perguntas", data=base).status_code == 302
    q = Q.query.filter_by(label="Usa óculos?").one(); assert q.options == ["Sim", "Não"] and not q.required
    for bad, msg in [({"options_text": "Só uma"}, "ao menos 2 opções"), ({"options_text": "A\nA"}, "opções únicas"), ({"label": ""}, "Informe a pergunta."), ({"position": -1}, "0 a 9999")]:
        assert auth_client.post("/anamnese/perguntas", data={**base, **bad}).status_code == 400
    assert auth_client.post("/anamnese/perguntas", data={**base, "label": "Observação", "field_type": "texto", "options_text": ""}).status_code == 302
    assert Q.query.filter_by(label="Observação").one().options is None                              # tipos sem opções não guardam lixo
    assert auth_client.post(f"/anamnese/perguntas/{q.id}/editar", data={**base, "label": "Usa lentes?"}).status_code == 302
    db.session.refresh(q); assert q.label == "Usa lentes?" and "Sim\nNão" in auth_client.get(f"/anamnese/perguntas/{q.id}/editar").get_data(as_text=True)


# ================= Satisfação =================
def done_appt(c, days=-3):
    a = Appointment(client_id=c.id, starts_at=now_local() + timedelta(days=days), duration_minutes=60, status=A.DONE); db.session.add(a); db.session.commit(); return a


def eform(c, **over):
    d = {"client_id": c.id, "appointment_id": 0, "score": 9, "comment": "Ótimo", "evaluated_on": today_local().isoformat()}; d.update(over); return d


def test_evaluation_crud_and_rules(auth_client):
    c = mk_client(); a = done_appt(c)
    assert auth_client.post("/satisfacao/nova", data=eform(c, appointment_id=a.id)).status_code == 302
    e = Evaluation.query.one(); assert (e.score, e.appointment_id, e.comment) == (9, a.id, "Ótimo")
    r = auth_client.post("/satisfacao/nova", data=eform(c, appointment_id=a.id))
    assert r.status_code == 400 and Evaluation.query.count() == 1                                    # uma avaliação por atendimento
    for over, msg in [({"score": 11}, "0 a 10"), ({"score": -1}, "0 a 10"), ({"score": ""}, "Informe a nota."),
                      ({"evaluated_on": (today_local() + timedelta(days=1)).isoformat()}, "não pode ser futura")]:
        r = auth_client.post("/satisfacao/nova", data=eform(c, **over)); assert r.status_code == 400 and msg in r.get_data(as_text=True)
    assert auth_client.post(f"/satisfacao/{e.id}/editar", data=eform(c, appointment_id=a.id, score=0, comment="")).status_code == 302
    db.session.refresh(e); assert e.score == 0 and e.comment is None                                 # nota 0 é válida
    auth_client.post(f"/satisfacao/{e.id}/excluir"); assert Evaluation.query.count() == 0


def test_evaluation_appointment_rules(auth_client):
    a, b = mk_client("A"), mk_client("B"); appt = done_appt(a)
    assert auth_client.post("/satisfacao/nova", data=eform(b, appointment_id=appt.id)).status_code == 400          # de outro cliente
    pending = Appointment(client_id=a.id, starts_at=now_local() + timedelta(days=5), duration_minutes=60); db.session.add(pending); db.session.commit()
    assert auth_client.post("/satisfacao/nova", data=eform(a, appointment_id=pending.id)).status_code == 400       # só realizados


def test_satisfaction_page_numbers(auth_client):
    c = mk_client()
    for s in (10, 9, 10, 8, 3):
        db.session.add(Evaluation(client_id=c.id, score=s, evaluated_on=today_local()))
    db.session.commit()
    html = auth_client.get("/satisfacao/").get_data(as_text=True)
    assert "8" in html and ">40<" in html and "data-chart=" in html                                  # NPS: 3 promotores, 1 detrator de 5 = 40


def test_nps_threshold_and_formula(app):
    assert an.nps([10, 10, 10, 10]) is None and an.nps([]) is None
    assert an.nps([10, 9, 9, 8, 7]) == 60 and an.nps([0, 6, 5, 6, 10]) == -60 and an.nps([7, 8, 7, 8, 7]) == 0 and an.nps([9] * 5) == 100


def test_nps_hidden_without_enough_data(auth_client):
    c = mk_client(); db.session.add(Evaluation(client_id=c.id, score=10, evaluated_on=today_local())); db.session.commit()
    assert "Disponível a partir de 5 avaliações" in auth_client.get("/satisfacao/").get_data(as_text=True)


# ================= Indicadores e Dashboard =================
def test_indicator_definitions(app):
    p = parse_period({"periodo": "tudo"}); c1, c2 = mk_client("Recorrente"), mk_client("Novo")
    for d in (-40, -10):
        done_appt(c1, d)
    done_appt(c2, -5)
    db.session.add_all([T(type=TT.INCOME, description="a", amount_cents=60000, date=today_local(), status=TS.PAID), T(type=TT.INCOME, description="p", amount_cents=99999, date=today_local(), status=TS.PENDING),
                        T(type=TT.EXPENSE, description="e", amount_cents=15000, date=today_local(), status=TS.PAID)]); db.session.commit()
    i = an.indicators(p)
    assert (i.income, i.expense, i.profit) == (60000, 15000, 45000)
    assert i.ticket == 20000                                  # 60000 / 3 atendimentos realizados
    assert (i.clients_total, i.clients_new, i.clients_recurring) == (2, 2, 1)
    assert an.indicators(parse_period({"de": "2000-01-01", "ate": "2000-01-31"})).ticket is None       # sem atendimentos: sem ticket


def test_archived_clients_are_not_counted_as_active(app):
    mk_client("A"); mk_client("B", archived_at=datetime(2026, 1, 1))
    assert an.indicators(parse_period({"periodo": "tudo"})).clients_total == 1


def test_month_range_and_labels(app):
    p = parse_period({"periodo": "ano"}); months = an.month_range(p)
    assert months[0].month == 1 and months[-1] == today_local().replace(day=1) and len(months) <= 12
    assert an.month_label(today_local().replace(month=3, day=1)).startswith("mar/")
    assert len(an.month_range(parse_period({"periodo": "tudo"}))) == 12                                  # limitado a 12 meses
    assert an.heat_level(0, 10) == 0 and an.heat_level(1, 10) == 1 and an.heat_level(10, 10) == 5 and an.heat_level(5, 10) == 3 and an.heat_level(3, 0) == 0


def test_dashboard_empty_state_and_with_data(auth_client):
    html = auth_client.get("/dashboard/").get_data(as_text=True)
    assert "Dashboard" in html and "Sem dados" in html and "data-chart=" not in html
    c = mk_client(source="Instagram"); db.session.add_all([Project(client_id=c.id, name="F", style="Fine line", body_region_id=BodyRegion.query.filter_by(slug="braco").one().id),
        T(type=TT.INCOME, description="x", amount_cents=50000, date=today_local(), status=TS.PAID)]); db.session.commit()
    html = auth_client.get("/dashboard/").get_data(as_text=True)
    charts = [json.loads(m.replace("&#39;", "'").replace("&#34;", '"')) for m in re.findall(r"data-chart='([^']+)'", html)]
    assert len(charts) == 5 and {c["type"] for c in charts} == {"bar", "doughnut"}
    rev = next(c for c in charts if c["datasets"][0]["label"] == "Faturamento"); assert sum(rev["datasets"][0]["data"]) == 50000
    assert "Fine line" in html and "Instagram" in html and "R$ 500,00" in html


def test_dashboard_period_filter_and_garbage(auth_client):
    for q in ("?periodo=ano", "?periodo=tudo", "?de=2026-01-01&ate=2026-12-31", "?de=x&ate=y", "?periodo=lixo"):
        assert auth_client.get("/dashboard/" + q).status_code == 200, q


# ================= Mapa corporal =================
def test_body_map_counts_exclude_canceled_and_color_by_intensity(auth_client):
    c = mk_client(); r = {x.slug: x.id for x in BodyRegion.query}
    db.session.add_all([Project(client_id=c.id, name=f"B{i}", body_region_id=r["braco"], style="Fine line") for i in range(4)]
                       + [Project(client_id=c.id, name="C", body_region_id=r["costas"], style="Blackwork"), Project(client_id=c.id, name="X", body_region_id=r["pe"], status=P.CANCELED)]); db.session.commit()
    html = auth_client.get("/preferencias-corporais/").get_data(as_text=True)
    assert "Braço: 4 projetos" in html and "Costas: 1 projeto" in html and "Pé: 0 projetos" in html          # cancelado não conta
    assert 'class="zone heat-5" data-region="braco"' in html and 'class="zone heat-0" data-region="pe"' in html
    assert html.count('data-region="braco"') == 2 and html.count('data-region="costas"') == 1                 # esquerdo/direito; costas só no verso
    assert "Fine line (4)" in html and "5 projetos" in html and "data-chart=" in html
    assert 'class="zone heat-' in auth_client.get("/preferencias-corporais/?periodo=mes").get_data(as_text=True)


def test_body_map_empty_and_all_13_regions_present(auth_client):
    html = auth_client.get("/preferencias-corporais/").get_data(as_text=True)
    assert "Sem dados" in html and "0 projetos" in html
    for slug in ("cabeca", "pescoco", "ombro", "braco", "antebraco", "mao", "peito", "abdomen", "costas", "quadril", "coxa", "panturrilha", "pe"):
        assert f'data-region="{slug}"' in html, slug


def test_new_pages_comply_with_csp(auth_client):
    c = mk_client(); db.session.add(Evaluation(client_id=c.id, score=9, evaluated_on=today_local())); db.session.commit()
    for path in ("/dashboard/", "/satisfacao/", "/preferencias-corporais/", "/financeiro/", "/estoque/", "/anamnese/nova", "/anamnese/perguntas", "/configuracoes/perfil"):
        html = auth_client.get(path).get_data(as_text=True)
        assert ' style="' not in html and not re.search(r"<script(?![^>]*\bsrc=)", html) and not re.search(r"\son[a-z]+=\"", html), path
