from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.extensions import db
from app.models import (ActivityLog, AnamnesisResponse, Appointment, Client, Evaluation,
                        FinancialTransaction, Project, ProjectReference, Quote)
from app.models.enums import (AppointmentStatus, PaymentMethod, ProjectStatus, QuoteStatus,
                              TransactionStatus, TransactionType)
from app.utils.dates import now_local, today_local

VALID = {"name": "Marina Lopes", "phone": "(71) 99999-0000", "email": "Marina@Example.com",
         "instagram": "@marina.tattoo", "birth_date": "1995-04-12", "source": "Instagram", "notes": "Pele sensível"}


def make_client(name="Cliente", **kw):
    c = Client(name=name, **kw)
    db.session.add(c)
    db.session.commit()
    return c


# ---------- Acesso ----------
@pytest.mark.parametrize("method,path", [
    ("get", "/clientes/"), ("get", "/clientes/novo"), ("post", "/clientes/novo"), ("get", "/clientes/1"),
    ("get", "/clientes/1/editar"), ("post", "/clientes/1/arquivar"), ("post", "/clientes/1/restaurar"),
    ("post", "/clientes/1/excluir-dados"),
])
def test_all_routes_require_login(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_post_without_csrf_token_is_rejected(app, auth_client):
    app.config["WTF_CSRF_ENABLED"] = True
    assert auth_client.post("/clientes/novo", data=VALID).status_code == 400
    assert Client.query.count() == 0


# ---------- Criar ----------
def test_create_client_normalizes_data(auth_client):
    r = auth_client.post("/clientes/novo", data=VALID)
    assert r.status_code == 302
    c = Client.query.one()
    assert c.email == "marina@example.com"          # minúsculo
    assert c.instagram == "marina.tattoo"           # sem @
    assert c.birth_date == date(1995, 4, 12)
    assert ActivityLog.query.filter_by(action="created", entity_id=c.id).count() == 1


def test_create_minimal_client_turns_blanks_into_none(auth_client):
    auth_client.post("/clientes/novo", data={"name": "  Só Nome  ", "source": ""})
    c = Client.query.one()
    assert c.name == "Só Nome"
    assert c.phone is None and c.email is None and c.instagram is None and c.notes is None


@pytest.mark.parametrize("field,value,message", [
    ("name", "", "Informe o nome."),
    ("email", "não-é-email", "E-mail inválido."),
    ("phone", "abc", "Telefone inválido"),
    ("phone", "123", "Telefone inválido"),
    ("phone", "٧١٩٩٩٩٩٠٠٠٠", "Telefone inválido"),   # dígitos de outro alfabeto
    ("instagram", "nome com espaço", "Usuário inválido"),
    ("birth_date", (date.today() + timedelta(days=1)).isoformat(), "Data de nascimento inválida"),
    ("birth_date", "1850-01-01", "Data de nascimento inválida"),
])
def test_create_validation_errors(auth_client, field, value, message):
    r = auth_client.post("/clientes/novo", data={**VALID, field: value})
    assert r.status_code == 400
    assert message in r.get_data(as_text=True)
    assert Client.query.count() == 0


def test_invalid_source_is_rejected(auth_client):
    assert auth_client.post("/clientes/novo", data={**VALID, "source": "inventado"}).status_code == 400


def test_form_keeps_typed_values_on_error(auth_client):
    html = auth_client.post("/clientes/novo", data={**VALID, "email": "ruim"}).get_data(as_text=True)
    assert 'value="Marina Lopes"' in html


# ---------- Lista: busca, filtro, paginação ----------
def test_list_empty_state(auth_client):
    assert "Nenhum cliente cadastrado ainda" in auth_client.get("/clientes/").get_data(as_text=True)


def test_search_by_name_phone_email_and_instagram(auth_client):
    make_client("Marina Lopes", phone="(71) 98888-1111", email="m@ex.com", instagram="mari.ink")
    make_client("Caio Ferraz", phone="(11) 97777-2222")
    for term, expected, absent in [("marina", "Marina Lopes", "Caio"), ("97777", "Caio Ferraz", "Marina"),
                                   ("m@ex", "Marina Lopes", "Caio"), ("@mari.ink", "Marina Lopes", "Caio")]:
        html = auth_client.get("/clientes/", query_string={"q": term}).get_data(as_text=True)
        assert expected in html and absent not in html, term


def test_search_treats_wildcards_literally(auth_client):
    make_client("Ana"); make_client("100% Couro")
    html = auth_client.get("/clientes/", query_string={"q": "%"}).get_data(as_text=True)
    assert "100% Couro" in html and ">Ana<" not in html
    assert ">Ana<" not in auth_client.get("/clientes/", query_string={"q": "_"}).get_data(as_text=True)


def test_search_no_results_state(auth_client):
    make_client("Ana")
    assert "Nenhum cliente encontrado" in auth_client.get("/clientes/", query_string={"q": "zzz"}).get_data(as_text=True)


def test_status_filter(auth_client):
    make_client("Ativa")
    make_client("Antiga", archived_at=datetime(2026, 1, 1))
    get = lambda s: auth_client.get("/clientes/", query_string={"status": s}).get_data(as_text=True)
    assert "Ativa" in get("ativos") and "Antiga" not in get("ativos")
    assert "Antiga" in get("arquivados") and "Ativa" not in get("arquivados")
    assert "Ativa" in get("todos") and "Antiga" in get("todos")
    assert "Antiga" not in get("invalido")           # valor inválido cai em "ativos"


def test_pagination_and_alphabetical_order(auth_client):
    for i in range(20):
        make_client(f"Cliente {i:02d}")
    p1 = auth_client.get("/clientes/").get_data(as_text=True)
    p2 = auth_client.get("/clientes/?page=2").get_data(as_text=True)
    assert "Cliente 00" in p1 and "Cliente 14" in p1 and "Cliente 15" not in p1
    assert "Cliente 15" in p2 and "Cliente 19" in p2
    assert 'aria-label="Paginação"' in p1 and "20 clientes" in p1
    assert auth_client.get("/clientes/?page=999").status_code == 200   # fora do intervalo: sem erro


def test_pagination_keeps_filters(auth_client):
    for i in range(20):
        make_client(f"Ana {i:02d}")
    html = auth_client.get("/clientes/", query_string={"q": "Ana"}).get_data(as_text=True)
    assert "q=Ana" in html and "page=2" in html


# ---------- Segurança de saída ----------
def test_user_content_is_escaped(auth_client):
    c = make_client("<script>alert(1)</script>", notes="<img src=x onerror=alert(1)>", instagram="ok")
    for path in ("/clientes/", f"/clientes/{c.id}", f"/clientes/{c.id}?aba=observacoes", f"/clientes/{c.id}/editar"):
        html = auth_client.get(path).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html, path
        assert "<img src=x" not in html, path


# ---------- Detalhe ----------
def test_detail_404_for_unknown_client(auth_client):
    assert auth_client.get("/clientes/9999").status_code == 404


def test_all_tabs_render_and_unknown_tab_falls_back(auth_client):
    c = make_client("Marina")
    for tab in ("resumo", "projetos", "agenda", "orcamentos", "pagamentos", "anamnese", "avaliacoes", "observacoes"):
        r = auth_client.get(f"/clientes/{c.id}", query_string={"aba": tab})
        assert r.status_code == 200, tab
        assert f"aba={tab}" in r.get_data(as_text=True)
    html = auth_client.get(f"/clientes/{c.id}?aba=../../etc/passwd").get_data(as_text=True)
    assert "Histórico completo" in html              # caiu no Resumo


def test_detail_marks_current_tab(auth_client):
    c = make_client("Marina")
    html = auth_client.get(f"/clientes/{c.id}?aba=agenda").get_data(as_text=True)
    assert 'aria-current="page">Agenda<' in html


def test_lgpd_erasure_deletes_personal_records_and_unlinks_finances(app, auth_client):
    from app.services.activity_service import log_activity

    c = make_client("Marina Lopes", phone="(71) 99999-0000", email="marina@example.com", notes="DADO-PRIVADO")
    _populate(c)
    project = Project.query.filter_by(client_id=c.id).one()
    appointment = Appointment.query.filter_by(client_id=c.id).order_by(Appointment.starts_at).first()
    today = today_local()
    transaction = FinancialTransaction(
        type=TransactionType.INCOME, description="Marina Lopes - pagamento", notes="OBS-PRIVADA",
        amount_cents=12345, date=today, client_id=c.id, project_id=project.id,
        appointment_id=appointment.id, status=TransactionStatus.PAID,
    )
    db.session.add(transaction)
    db.session.flush()
    transaction_id = transaction.id
    log_activity("updated", "Marina Lopes - pagamento alterado", None, "transaction", transaction_id)
    reference = ProjectReference(project_id=project.id, stored_filename="lgpd-test.webp",
                                 original_filename="Marina Lopes.jpg")
    db.session.add(reference)
    db.session.commit()
    images = Path(app.config["UPLOAD_FOLDER"]) / "projects"
    images.mkdir(parents=True)
    (images / "lgpd-test.webp").write_bytes(b"image")
    (images / "lgpd-test_thumb.webp").write_bytes(b"thumb")

    response = auth_client.post(f"/clientes/{c.id}/excluir-dados")

    assert response.status_code == 302
    assert db.session.get(Client, c.id) is None
    assert Project.query.count() == 0
    assert Appointment.query.count() == 0
    assert Quote.query.count() == 0
    assert AnamnesisResponse.query.count() == 0
    assert Evaluation.query.count() == 0
    kept = db.session.get(FinancialTransaction, transaction_id)
    assert kept.amount_cents == 12345 and kept.date == today and kept.status == TransactionStatus.PAID
    assert kept.client_id is None and kept.project_id is None and kept.appointment_id is None
    assert kept.description == "Lançamento financeiro de cliente desvinculado"
    assert kept.notes is None and kept.supplier is None
    assert not (images / "lgpd-test.webp").exists()
    assert not (images / "lgpd-test_thumb.webp").exists()
    logs = [log.description for log in ActivityLog.query.all()]
    assert any("Dados de cliente eliminados" in value for value in logs)
    assert all("Marina Lopes" not in value and "OBS-PRIVADA" not in value for value in logs)


def test_sidebar_keeps_clients_active_on_detail(auth_client):
    c = make_client("Marina")
    html = auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)
    assert 'href="/clientes" title="Clientes" aria-current="page"' in html


def _populate(c):
    today = today_local()
    p = Project(client_id=c.id, name="Floral", status=ProjectStatus.IN_PROGRESS, style="Fine line", price_cents=120000)
    db.session.add(p); db.session.flush()
    a_done = Appointment(client_id=c.id, project_id=p.id, starts_at=now_local() - timedelta(days=10), service="Sessão 1",
                         status=AppointmentStatus.DONE)
    a_next = Appointment(client_id=c.id, starts_at=now_local() + timedelta(days=3), service="Sessão 2",
                         status=AppointmentStatus.CONFIRMED)
    db.session.add_all([
        a_done, a_next,
        Quote(client_id=c.id, description="Floral", price_cents=120000, status=QuoteStatus.APPROVED, valid_until=today),
        FinancialTransaction(type=TransactionType.INCOME, description="Sinal", amount_cents=30000, date=today,
                             client_id=c.id, status=TransactionStatus.PAID, payment_method=PaymentMethod.PIX),
        FinancialTransaction(type=TransactionType.INCOME, description="Restante", amount_cents=90000, date=today,
                             client_id=c.id, status=TransactionStatus.PENDING),
        FinancialTransaction(type=TransactionType.EXPENSE, description="Material", amount_cents=5000, date=today,
                             client_id=c.id, status=TransactionStatus.PAID),   # despesa não é pagamento do cliente
        AnamnesisResponse(client_id=c.id, answers=[{"label": "Alergias?", "value": "SEGREDO-SAUDE"}], accepted=True),
    ])
    db.session.flush()
    db.session.add_all([Evaluation(client_id=c.id, appointment_id=a_done.id, score=10, comment="Amei", evaluated_on=today),
                        Evaluation(client_id=c.id, score=8, evaluated_on=today)])
    db.session.commit()


def test_summary_numbers_and_history_come_from_database(auth_client):
    c = make_client("Marina")
    _populate(c)
    html = auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)
    assert "R$ 300,00" in html                       # só receitas pagas
    assert "A receber: R$ 900,00" in html
    assert "9/10" in html and "2 avaliações" in html
    for text in ("Projeto: Floral", "Atendimento realizado", "Atendimento confirmado", "Orçamento aprovado",
                 "Pagamento pago: R$ 300,00", "Avaliação: 10/10", "Ficha de anamnese registrada"):
        assert text in html, text
    assert "Material" not in html                    # despesa fora do histórico do cliente


def test_average_score_uses_brazilian_decimal(auth_client):
    c = make_client("Marina")
    db.session.add_all([Evaluation(client_id=c.id, score=9, evaluated_on=today_local()),
                        Evaluation(client_id=c.id, score=8, evaluated_on=today_local())])
    db.session.commit()
    assert "8,5/10" in auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)


def test_tabs_show_related_records(auth_client):
    c = make_client("Marina")
    _populate(c)
    get = lambda tab: auth_client.get(f"/clientes/{c.id}", query_string={"aba": tab}).get_data(as_text=True)
    assert "Floral" in get("projetos") and "Fine line" in get("projetos") and "Em andamento" in get("projetos")
    assert "Sessão 1" in get("agenda") and "Sessão 2" in get("agenda")
    assert "R$ 1.200,00" in get("orcamentos") and "Aprovado" in get("orcamentos")
    pag = get("pagamentos")
    assert "Sinal" in pag and "Restante" in pag and "Pix" in pag and "Material" not in pag
    assert "Amei" in get("avaliacoes") and "Promotor" in get("avaliacoes")


def test_anamnesis_tab_never_leaks_health_answers(auth_client):
    c = make_client("Marina")
    _populate(c)
    html = auth_client.get(f"/clientes/{c.id}?aba=anamnese").get_data(as_text=True)
    assert "Ficha de" in html and "Aceita" in html
    assert "SEGREDO-SAUDE" not in html and "Alergias" not in html
    assert "SEGREDO-SAUDE" not in auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)


def test_other_clients_data_does_not_leak(auth_client):
    a, b = make_client("A"), make_client("B")
    db.session.add(Project(client_id=b.id, name="Projeto do B"))
    db.session.commit()
    assert "Projeto do B" not in auth_client.get(f"/clientes/{a.id}?aba=projetos").get_data(as_text=True)


# ---------- Editar / arquivar / restaurar ----------
def test_edit_updates_and_logs(auth_client):
    c = make_client("Antigo", phone="(71) 90000-0000")
    assert "Antigo" in auth_client.get(f"/clientes/{c.id}/editar").get_data(as_text=True)
    r = auth_client.post(f"/clientes/{c.id}/editar", data={**VALID, "name": "Novo Nome"})
    assert r.status_code == 302
    db.session.refresh(c)
    assert c.name == "Novo Nome" and c.email == "marina@example.com"
    assert ActivityLog.query.filter_by(action="updated", entity_id=c.id).count() == 1


def test_edit_validation_error_does_not_change_data(auth_client):
    c = make_client("Fica Assim")
    assert auth_client.post(f"/clientes/{c.id}/editar", data={**VALID, "email": "x"}).status_code == 400
    db.session.refresh(c)
    assert c.name == "Fica Assim"


def test_archive_requires_post_and_preserves_history(auth_client):
    c = make_client("Marina")
    _populate(c)
    assert auth_client.get(f"/clientes/{c.id}/arquivar").status_code == 405
    assert auth_client.post(f"/clientes/{c.id}/arquivar").status_code == 302
    db.session.refresh(c)
    assert c.is_archived and Client.query.count() == 1
    assert Project.query.count() == 1 and FinancialTransaction.query.count() == 3   # nada foi apagado
    listing = auth_client.get("/clientes/").get_data(as_text=True)
    assert f'href="/clientes/{c.id}"' not in listing          # some da lista (o aviso cita o nome, por isso o link)
    page = auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)
    assert "está arquivado" in page and "Restaurar" in page
    assert ActivityLog.query.filter_by(action="archived", entity_id=c.id).count() == 1


def test_restore(auth_client):
    c = make_client("Marina", archived_at=datetime(2026, 1, 1))
    assert auth_client.post(f"/clientes/{c.id}/restaurar").status_code == 302
    db.session.refresh(c)
    assert not c.is_archived
    assert f'href="/clientes/{c.id}"' in auth_client.get("/clientes/").get_data(as_text=True)


def test_archive_button_has_confirmation(auth_client):
    c = make_client("Marina")
    html = auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)
    assert "data-confirm=" in html and "Arquivar Marina?" in html
