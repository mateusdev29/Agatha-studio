"""Sinal do atendimento no Financeiro: vínculo, idempotência, sincronia, remarcação e cancelamento."""
import re
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import ActivityLog, Appointment, Category, Client, FinancialTransaction as T, Project
from app.models.enums import (AppointmentStatus as A, CategoryKind, PaymentMethod, TransactionStatus as TS, TransactionType as TT)
from app.services import deposit_service as dep
from app.utils.dates import today_local


def at(days=10, h=10):
    return datetime.combine(today_local() + timedelta(days=days), time(h))


def mk(name="Marina Lopes", deposit=15000, price=60000, status=A.CONFIRMED, days=10, project=False, **kw):
    c = Client(name=name); db.session.add(c); db.session.flush()
    p = None
    if project:
        p = Project(client_id=c.id, name="Floral"); db.session.add(p); db.session.flush()
    a = Appointment(client_id=c.id, project_id=p.id if p else None, starts_at=at(days), duration_minutes=60, status=status,
                    service=kw.pop("service", "Sessão"), price_cents=price, deposit_cents=deposit, **kw)
    db.session.add(a); db.session.commit(); return a


def launch(c, a, **over):
    d = {"payment_method": "pix", "date": today_local().isoformat(), "status": "pago"}; d.update(over)
    return c.post(f"/agenda/{a.id}/sinal", data=d)


def deposits(a=None):
    q = T.query.filter_by(is_deposit=True)
    return q.filter_by(appointment_id=a.id).all() if a else q.all()


# ---------- lançar ----------
def test_launch_creates_a_fully_linked_income(auth_client):
    a = mk(project=True)
    r = launch(auth_client, a)
    t = T.query.one()
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/agenda/{a.id}")
    assert (t.type, t.amount_cents, t.status, t.payment_method, t.date) == (TT.INCOME, 15000, TS.PAID, PaymentMethod.PIX, today_local())
    assert (t.client_id, t.project_id, t.appointment_id, t.is_deposit, t.description) == (a.client_id, a.project_id, a.id, True, "Sinal: Sessão")
    assert t.category.name == "Sinal / Entrada" and t.category.kind == CategoryKind.INCOME
    assert ActivityLog.query.filter(ActivityLog.description.like("Sinal lançado%")).count() == 1


def test_launched_deposit_appears_everywhere_it_should(auth_client):
    a = mk(project=True); launch(auth_client, a)
    fin = auth_client.get("/financeiro/").get_data(as_text=True)
    assert "Sinal: Sessão" in fin and "R$ 150,00" in fin and ">Sinal<" in fin                      # lista + selo
    assert "Sinal: Sessão" in auth_client.get(f"/clientes/{a.client_id}?aba=pagamentos").get_data(as_text=True)
    assert "R$ 150,00" in auth_client.get(f"/projetos/{a.project_id}").get_data(as_text=True)       # "Pago" do projeto
    assert "R$ 150,00" in auth_client.get(f"/clientes/{a.client_id}").get_data(as_text=True)        # total pago do cliente
    assert "R$ 150,00" in auth_client.get("/dashboard/").get_data(as_text=True)                     # faturamento


def test_pending_deposit_is_receivable_until_marked_received(auth_client):
    a = mk(); launch(auth_client, a, status="pendente")
    fin = auth_client.get("/financeiro/").get_data(as_text=True)
    assert "A receber" in fin and "R$ 150,00" in fin
    from app.services.finance_service import summary
    from app.utils.periods import parse_period
    s = summary(parse_period({"periodo": "mes"})); assert (s.income, s.pending_in) == (0, 15000)
    page = auth_client.get(f"/agenda/{a.id}").get_data(as_text=True)
    assert "Marcar como recebido" in page
    t = T.query.one()
    r = auth_client.post(f"/financeiro/{t.id}/pagar", headers={"Referer": f"http://localhost/agenda/{a.id}"})
    assert r.headers["Location"].endswith(f"/agenda/{a.id}")                                        # volta para o atendimento
    s = summary(parse_period({"periodo": "mes"})); assert (s.income, s.pending_in) == (15000, 0)


# ---------- nunca duplicar ----------
def test_launching_twice_never_duplicates(auth_client):
    a = mk(); launch(auth_client, a)
    r = auth_client.post(f"/agenda/{a.id}/sinal", data={"payment_method": "pix", "date": today_local().isoformat(), "status": "pago"}, follow_redirects=True)
    assert "já foi lançado" in r.get_data(as_text=True) and len(deposits(a)) == 1


def test_database_blocks_a_second_deposit_even_if_the_service_is_bypassed(app):
    a = mk()
    make = lambda dep_flag: T(type=TT.INCOME, description="x", amount_cents=100, date=today_local(), appointment_id=a.id, is_deposit=dep_flag)
    db.session.add_all([make(True), make(False), make(False)]); db.session.commit()                 # várias NÃO-sinal podem existir
    db.session.add(make(True))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback(); assert T.query.filter_by(appointment_id=a.id).count() == 3


def test_race_condition_is_reported_not_crashed(app, monkeypatch):
    a = mk(); dep.launch_deposit(a, None, today_local(), TS.PAID, None)
    monkeypatch.setattr(dep, "deposit_transaction", lambda appt: None)                               # simula "outro clique" que ainda não viu o lançamento
    with pytest.raises(dep.DepositError, match="já foi lançado"):
        dep.launch_deposit(a, None, today_local(), TS.PAID, None)
    assert len(deposits(a)) == 1


# ---------- validações ----------
@pytest.mark.parametrize("kwargs,msg", [({"deposit": 0}, "não tem sinal combinado"), ({"status": A.CANCELED}, "cancelado ou remarcado"), ({"status": A.RESCHEDULED}, "cancelado ou remarcado")])
def test_launch_rules(auth_client, kwargs, msg):
    a = mk(**kwargs)
    r = auth_client.post(f"/agenda/{a.id}/sinal", data={"payment_method": "pix", "date": today_local().isoformat(), "status": "pago"}, follow_redirects=True)
    assert msg in r.get_data(as_text=True) and T.query.count() == 0


@pytest.mark.parametrize("over", [{"payment_method": "boleto"}, {"status": "cancelado"}, {"date": ""}, {"date": "1999-01-01"}, {"date": "lixo"}])
def test_launch_rejects_invalid_form_values(auth_client, over):
    a = mk(); launch(auth_client, a, **over); assert T.query.count() == 0


def test_launch_without_payment_method_and_without_category(auth_client):
    Category.query.filter_by(name="Sinal / Entrada").update({"is_active": False}); db.session.commit()
    a = mk(); launch(auth_client, a, payment_method="")
    t = T.query.one(); assert t.payment_method is None and t.category_id is None


def test_launch_requires_post(auth_client):
    a = mk(); assert auth_client.get(f"/agenda/{a.id}/sinal").status_code == 405


# ---------- tela do atendimento ----------
def test_detail_states(auth_client):
    page = lambda a: auth_client.get(f"/agenda/{a.id}").get_data(as_text=True)
    assert "Sem sinal combinado" in page(mk("A", deposit=0))
    unlaunched = page(mk("B")); assert "Lançar no Financeiro" in unlaunched and "ainda não lançado" in unlaunched
    c = mk("C"); launch(auth_client, c); p = page(c)
    assert "Ver no Financeiro" in p and "Lançar no Financeiro" not in p and "Marcar como recebido" not in p
    d = mk("D"); launch(auth_client, d, status="pendente"); assert "Marcar como recebido" in page(d)
    e = mk("E", status=A.CANCELED); assert "não lançado" in page(e) and "Lançar no Financeiro" not in page(e)


def test_xss_is_escaped_in_deposit_flow(auth_client):
    a = mk(service="<script>alert(1)</script>"); launch(auth_client, a)
    for path in (f"/agenda/{a.id}", "/financeiro/", f"/financeiro/{T.query.one().id}/editar", f"/clientes/{a.client_id}?aba=pagamentos"):
        assert "<script>alert(1)</script>" not in auth_client.get(path).get_data(as_text=True), path


# ---------- Financeiro é a fonte da verdade depois de lançado ----------
def aform(a, **over):
    d = {"client_id": a.client_id, "project_id": 0, "date": at().date().isoformat(), "time": "10:00", "duration_minutes": 60,
         "service": "Sessão", "price_cents": "600,00", "deposit_cents": "150,00", "notes": ""}; d.update(over); return d


def test_appointment_deposit_field_is_locked_after_launch(auth_client):
    a = mk(); html = auth_client.get(f"/agenda/{a.id}/editar").get_data(as_text=True)
    assert 'name="deposit_cents"' in html and "Já lançado no Financeiro" not in html                  # antes: editável
    assert auth_client.post(f"/agenda/{a.id}/editar", data=aform(a, deposit_cents="200,00")).status_code == 302
    db.session.refresh(a); assert a.deposit_cents == 20000
    launch(auth_client, a)                                                                            # lança os R$ 200,00
    html = auth_client.get(f"/agenda/{a.id}/editar").get_data(as_text=True)
    tag = re.search(r'<input[^>]*name="deposit_cents"[^>]*>', html).group(0)
    assert "Já lançado no Financeiro" in html and "disabled" in tag                                   # input realmente desabilitado
    auth_client.post(f"/agenda/{a.id}/editar", data=aform(a, deposit_cents="999,00", price_cents="1.000,00", service="Outra"))   # tentativa de burlar
    db.session.refresh(a); assert a.deposit_cents == 20000 and a.service == "Outra" and T.query.one().amount_cents == 20000


def fform(**over):
    d = {"description": "Sinal: Sessão", "category_id": 0, "amount_cents": "150,00", "date": today_local().isoformat(), "payment_method": "pix",
         "status": "pago", "client_id": 0, "project_id": 0, "supplier": "", "notes": ""}; d.update(over); return d


def test_editing_the_transaction_syncs_the_appointment_and_keeps_the_link(auth_client):
    a = mk(project=True); other = Client(name="Outro"); db.session.add(other); db.session.commit(); launch(auth_client, a); t = T.query.one()
    banner = auth_client.get(f"/financeiro/{t.id}/editar").get_data(as_text=True)
    assert "Sinal do atendimento de" in banner and f"/agenda/{a.id}" in banner
    r = auth_client.post(f"/financeiro/{t.id}/editar", data=fform(amount_cents="180,00", client_id=other.id, project_id=0, description="Sinal ajustado"))
    assert r.status_code == 302
    db.session.refresh(t); db.session.refresh(a)
    assert (t.amount_cents, a.deposit_cents) == (18000, 18000)                                         # Agenda acompanha
    assert (t.client_id, t.project_id, t.appointment_id, t.is_deposit) == (a.client_id, a.project_id, a.id, True)   # cliente/projeto seguem o atendimento


def test_deleting_the_transaction_frees_the_appointment(auth_client):
    a = mk(); launch(auth_client, a); t = T.query.one()
    auth_client.post(f"/financeiro/{t.id}/excluir")
    assert T.query.count() == 0 and "Lançar no Financeiro" in auth_client.get(f"/agenda/{a.id}").get_data(as_text=True)
    assert 'name="deposit_cents"' in auth_client.get(f"/agenda/{a.id}/editar").get_data(as_text=True)  # editável de novo
    launch(auth_client, a); assert len(deposits(a)) == 1                                              # e pode lançar de novo


# ---------- remarcar e cancelar ----------
def test_rescheduling_moves_the_deposit_without_duplicating_money(auth_client):
    a = mk(); launch(auth_client, a); t = T.query.one()
    r = auth_client.post(f"/agenda/{a.id}/remarcar", data={"date": at(17).date().isoformat(), "time": "15:00", "duration_minutes": 60})
    new = Appointment.query.filter(Appointment.id != a.id).one()
    db.session.refresh(t); db.session.refresh(a)
    assert r.headers["Location"].endswith(f"/agenda/{new.id}") and t.appointment_id == new.id and T.query.count() == 1
    assert (a.status, a.deposit_cents, new.deposit_cents) == (A.RESCHEDULED, 0, 15000)
    assert len(deposits(a)) == 0 and len(deposits(new)) == 1 and sum(x.amount_cents for x in T.query) == 15000
    assert "Ver no Financeiro" in auth_client.get(f"/agenda/{new.id}").get_data(as_text=True)
    again = auth_client.post(f"/agenda/{new.id}/sinal", data={"payment_method": "pix", "date": today_local().isoformat(), "status": "pago"}, follow_redirects=True)
    assert "já foi lançado" in again.get_data(as_text=True) and T.query.count() == 1


def test_rescheduling_without_a_launched_deposit_keeps_working(auth_client):
    a = mk(); auth_client.post(f"/agenda/{a.id}/remarcar", data={"date": at(17).date().isoformat(), "time": "15:00", "duration_minutes": 60})
    new = Appointment.query.filter(Appointment.id != a.id).one(); assert new.deposit_cents == 15000 and T.query.count() == 0
    launch(auth_client, new); assert len(deposits(new)) == 1


def test_canceling_never_touches_the_money_but_warns(auth_client):
    a = mk(); launch(auth_client, a); t = T.query.one()
    page = auth_client.get(f"/agenda/{a.id}").get_data(as_text=True)
    assert "NÃO será alterado" in page and "R$ 150,00" in page                                        # aviso no diálogo de confirmação
    auth_client.post(f"/agenda/{a.id}/cancelar"); db.session.refresh(t); db.session.refresh(a)
    assert a.status == A.CANCELED and (t.status, t.amount_cents, t.appointment_id) == (TS.PAID, 15000, a.id)
    assert "Atendimento cancelado: o lançamento não foi alterado" in auth_client.get(f"/agenda/{a.id}").get_data(as_text=True)
    auth_client.post(f"/agenda/{a.id}/reativar"); assert T.query.one().amount_cents == 15000


def test_pending_deposit_of_canceled_appointment_is_left_for_the_user(auth_client):
    a = mk(); launch(auth_client, a, status="pendente"); auth_client.post(f"/agenda/{a.id}/cancelar")
    assert T.query.one().status == TS.PENDING                                                          # nada é cancelado/apagado automaticamente
    assert "NÃO será alterado" not in auth_client.get(f"/agenda/{a.id}").get_data(as_text=True)       # (só avisa quando já foi recebido)
