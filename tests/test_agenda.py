from datetime import date, datetime, time, timedelta

import pytest

from app.extensions import db
from app.models import ActivityLog, Appointment, Client, Project, ProjectSession
from app.models.enums import AppointmentStatus as S
from app.services import appointment_service as svc
from app.services import calendar_service as cal
from app.utils.dates import today_local


def mk_client(name="Marina Lopes", **kw):
    c = Client(name=name, **kw); db.session.add(c); db.session.commit(); return c


def at(days=10, h=10, m=0):
    return datetime.combine(today_local() + timedelta(days=days), time(h, m))


def mk_appt(client, start=None, dur=60, status=S.WAITING, **kw):
    a = Appointment(client_id=client.id, starts_at=start or at(), duration_minutes=dur, status=status, **kw)
    db.session.add(a); db.session.commit(); return a


def form(client, start=None, **over):
    start = start or at()
    d = {"client_id": client.id, "project_id": 0, "date": start.date().isoformat(), "time": start.strftime("%H:%M"),
         "duration_minutes": 90, "service": "Sessão", "price_cents": "600,00", "deposit_cents": "100,00", "notes": "obs"}
    d.update(over); return d


def act(client, appt, action):
    return client.post(f"/agenda/{appt.id}/{action}")


# ---------- Acesso ----------
@pytest.mark.parametrize("method,path", [
    ("get", "/agenda/"), ("get", "/agenda/novo"), ("post", "/agenda/novo"), ("get", "/agenda/1"), ("get", "/agenda/1/editar"),
    ("post", "/agenda/1/confirmar"), ("post", "/agenda/1/realizar"), ("post", "/agenda/1/cancelar"),
    ("post", "/agenda/1/reativar"), ("get", "/agenda/1/remarcar"), ("post", "/agenda/1/remarcar"),
])
def test_all_routes_require_login(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# ---------- Calendário (regras puras) ----------
def test_parse_fallbacks(app):
    assert cal.parse_view("dia") == "dia" and cal.parse_view("xyz") == "semana" and cal.parse_view(None) == "semana"
    assert cal.parse_date("2026-10-01") == date(2026, 10, 1)
    for bad in (None, "", "lixo", "2026-13-40", "1850-01-01", "2500-01-01"):
        assert cal.parse_date(bad) == today_local()


def test_week_starts_on_monday_and_has_seven_days(app):
    c = cal.build_calendar("semana", date(2026, 10, 1))        # quinta-feira
    assert [d.date for d in c.days][0] == date(2026, 9, 28) and len(c.days) == 7 and c.days[0].date.weekday() == 0
    assert c.prev == date(2026, 9, 24) and c.next == date(2026, 10, 8) and c.title == "28 set – 4 out 2026"


@pytest.mark.parametrize("anchor", [date(2026, 2, 10), date(2026, 3, 1), date(2026, 8, 31), date(2027, 1, 15), date(2024, 2, 29)])
def test_month_grid_is_whole_weeks_covering_the_month(app, anchor):
    c = cal.build_calendar("mes", anchor)
    assert len(c.days) % 7 == 0 and c.days[0].date.weekday() == 0 and c.days[-1].date.weekday() == 6
    inside = [d.date for d in c.days if d.in_range]
    assert inside[0].day == 1 and inside[-1] == (cal._shift_month(anchor.replace(day=1), 1) - timedelta(days=1))
    assert len(inside) == len(set(inside))


def test_month_navigation_crosses_year(app):
    assert cal.build_calendar("mes", date(2026, 12, 20)).next == date(2027, 1, 1)
    assert cal.build_calendar("mes", date(2026, 1, 20)).prev == date(2025, 12, 1)
    assert cal.build_calendar("mes", date(2026, 3, 5)).title == "março de 2026"


def test_day_title_and_navigation(app):
    c = cal.build_calendar("dia", date(2026, 9, 30))
    assert c.title == "quarta-feira, 30 de setembro de 2026" and c.prev == date(2026, 9, 29) and c.next == date(2026, 10, 1)


def test_appointments_are_grouped_by_day_with_midnight_boundaries(app):
    c1 = mk_client(); d = date(2026, 10, 1)
    late = mk_appt(c1, datetime(2026, 10, 1, 23, 30)); midnight = mk_appt(c1, datetime(2026, 10, 2, 0, 0))
    early = mk_appt(c1, datetime(2026, 10, 1, 0, 0), dur=30)
    day1, day2 = cal.build_calendar("dia", d).days[0], cal.build_calendar("dia", date(2026, 10, 2)).days[0]
    assert [a.id for a in day1.items] == [early.id, late.id] and [a.id for a in day2.items] == [midnight.id]
    week = cal.build_calendar("semana", d)
    assert sum(len(x.items) for x in week.days) == 3


# ---------- Telas ----------
def test_views_render_and_survive_garbage_params(auth_client):
    c = mk_client(); mk_appt(c, at(0, 14), status=S.CONFIRMED)
    for q in ("", "?vista=dia", "?vista=semana", "?vista=mes", "?vista=xyz&data=lixo", "?data=2026-02-30", "?vista=mes&data=1000-01-01"):
        assert auth_client.get("/agenda/" + q).status_code == 200, q


def test_chip_and_states_are_displayed(auth_client):
    c = mk_client("Marina Lopes")
    mk_appt(c, at(0, 14), status=S.CONFIRMED); mk_appt(c, at(0, 16), status=S.CANCELED)
    week = auth_client.get("/agenda/?vista=semana").get_data(as_text=True)
    assert "chip-success" in week and "is-off" in week and ">14:00</span>Marina" in week and "is-today" in week
    assert "Dia livre" in auth_client.get(f"/agenda/?vista=dia&data={at(30).date().isoformat()}").get_data(as_text=True)
    day = auth_client.get("/agenda/?vista=dia").get_data(as_text=True)
    assert "14:00" in day and "até 15:00" in day and "Confirmado" in day


def test_month_view_shows_overflow_and_counts(auth_client):
    c = mk_client(); day = at(0)
    for i in range(5):
        mk_appt(c, day.replace(hour=8 + i), dur=30)
    html = auth_client.get("/agenda/?vista=mes").get_data(as_text=True)
    assert "+2 mais" in html and 'aria-label="5 atendimentos"' in html


def test_view_switcher_marks_current(auth_client):
    html = auth_client.get("/agenda/?vista=mes").get_data(as_text=True)
    assert 'aria-current="page">Mês<' in html and 'href="/agenda" title="Agenda" aria-current="page"' in html


# ---------- Criar ----------
def test_create_appointment(auth_client):
    c = mk_client(); start = at()
    r = auth_client.post("/agenda/novo", data=form(c, start))
    a = Appointment.query.one()
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/agenda/{a.id}")
    assert (a.starts_at, a.duration_minutes, a.price_cents, a.deposit_cents, a.status) == (start, 90, 60000, 10000, S.WAITING)
    assert ActivityLog.query.filter_by(action="created", entity_type="appointment").count() == 1


def test_create_prefill_from_query(auth_client):
    c = mk_client(); p = Project(client_id=c.id, name="Floral"); db.session.add(p); db.session.commit()
    html = auth_client.get(f"/agenda/novo?cliente={c.id}&projeto={p.id}&data=2026-12-24").get_data(as_text=True)
    assert f'<option selected value="{c.id}">' in html and f'<option selected value="{p.id}"' in html and 'value="2026-12-24"' in html


@pytest.mark.parametrize("over,msg", [
    ({"date": ""}, "Informe a data."), ({"time": ""}, "Informe o horário."), ({"duration_minutes": "5"}, "Use de 15 a 720"),
    ({"duration_minutes": "9999"}, "Use de 15 a 720"), ({"price_cents": "x"}, "Valor inválido"),
    ({"deposit_cents": "700,00"}, "sinal não pode ser maior"), ({"client_id": 999}, "Not a valid choice"),
    ({"date": "1999-01-01"}, "Data inválida"), ({"project_id": 999}, "Not a valid choice"),
])
def test_create_validation(auth_client, over, msg):
    c = mk_client()
    r = auth_client.post("/agenda/novo", data=form(c, **over))
    assert r.status_code == 400 and msg in r.get_data(as_text=True) and Appointment.query.count() == 0


def test_project_must_belong_to_client(auth_client):
    a, b = mk_client("A"), mk_client("B"); p = Project(client_id=b.id, name="Do B"); db.session.add(p); db.session.commit()
    r = auth_client.post("/agenda/novo", data=form(a, project_id=p.id))
    assert r.status_code == 400 and "não pertence ao cliente" in r.get_data(as_text=True) and Appointment.query.count() == 0
    assert auth_client.post("/agenda/novo", data=form(b, project_id=p.id)).status_code == 302


def test_project_select_carries_group_for_js_filter(auth_client):
    a = mk_client("A"); p = Project(client_id=a.id, name="Floral"); db.session.add(p); db.session.commit()
    html = auth_client.get("/agenda/novo").get_data(as_text=True)
    assert f'data-group="{a.id}"' in html and 'data-depends-on="client_id"' in html


def test_archived_client_cannot_be_scheduled(auth_client):
    c = mk_client(archived_at=datetime(2026, 1, 1))
    assert auth_client.post("/agenda/novo", data=form(c)).status_code == 400


def test_past_appointments_can_be_registered(auth_client):
    c = mk_client()
    assert auth_client.post("/agenda/novo", data=form(c, at(-30))).status_code == 302


# ---------- Conflitos ----------
def test_overlap_is_rejected_with_clear_message(auth_client):
    a, b = mk_client("Ana"), mk_client("Bia"); mk_appt(a, at(10, 10), 120)
    for h, m in ((10, 0), (11, 30), (9, 30)):
        r = auth_client.post("/agenda/novo", data=form(b, at(10, h, m)))
        assert r.status_code == 400 and "Conflito de horário com Ana (10:00–12:00)" in r.get_data(as_text=True), (h, m)
    assert Appointment.query.count() == 1


def test_adjacent_appointments_are_allowed(auth_client):
    a, b = mk_client("Ana"), mk_client("Bia"); mk_appt(a, at(10, 10), 120)
    assert auth_client.post("/agenda/novo", data=form(b, at(10, 12, 0), duration_minutes=60)).status_code == 302
    assert auth_client.post("/agenda/novo", data=form(b, at(10, 8, 0), duration_minutes=120)).status_code == 302


def test_canceled_and_rescheduled_free_the_slot_but_done_blocks(auth_client):
    a, b = mk_client("Ana"), mk_client("Bia")
    mk_appt(a, at(10, 10), 60, S.CANCELED); mk_appt(a, at(11, 10), 60, S.RESCHEDULED); mk_appt(a, at(-5, 10), 60, S.DONE)
    assert auth_client.post("/agenda/novo", data=form(b, at(10, 10))).status_code == 302
    assert auth_client.post("/agenda/novo", data=form(b, at(11, 10))).status_code == 302
    assert auth_client.post("/agenda/novo", data=form(b, at(-5, 10, 30))).status_code == 400


def test_long_appointment_conflicts_with_a_much_later_start(app):
    c = mk_client(); mk_appt(c, at(10, 6), 720)               # 06:00–18:00
    assert svc.find_conflict(at(10, 17, 30), 30) is not None
    assert svc.find_conflict(at(10, 18, 0), 30) is None


# ---------- Editar ----------
def test_edit_keeps_own_slot_and_blocks_others(auth_client):
    a, b = mk_client("Ana"), mk_client("Bia"); x = mk_appt(a, at(10, 10), 60); mk_appt(b, at(10, 12), 60)
    assert auth_client.post(f"/agenda/{x.id}/editar", data=form(a, at(10, 10), duration_minutes=90)).status_code == 302
    db.session.refresh(x); assert x.duration_minutes == 90
    r = auth_client.post(f"/agenda/{x.id}/editar", data=form(a, at(10, 11, 30)))
    assert r.status_code == 400 and "Conflito" in r.get_data(as_text=True)
    page = auth_client.get(f"/agenda/{x.id}/editar").get_data(as_text=True)
    assert 'value="10:00"' in page and f'value="{at(10).date().isoformat()}"' in page


@pytest.mark.parametrize("status", [S.DONE, S.CANCELED, S.RESCHEDULED])
def test_closed_appointments_cannot_be_edited(auth_client, status):
    c = mk_client(); x = mk_appt(c, status=status)
    r = auth_client.get(f"/agenda/{x.id}/editar", follow_redirects=True)
    assert "Só atendimentos aguardando ou confirmados" in r.get_data(as_text=True)
    assert auth_client.post(f"/agenda/{x.id}/editar", data=form(c, service="Mudou")).status_code == 302
    db.session.refresh(x); assert x.service is None


# ---------- Transições ----------
def test_confirm_finish_cancel_reactivate_flow(auth_client):
    c = mk_client(); x = mk_appt(c, at(-1, 10))
    for action, expected in [("confirmar", S.CONFIRMED), ("realizar", S.DONE)]:
        act(auth_client, x, action); db.session.refresh(x); assert x.status == expected
    y = mk_appt(c, at(5, 10))
    act(auth_client, y, "cancelar"); db.session.refresh(y); assert y.status == S.CANCELED
    act(auth_client, y, "reativar"); db.session.refresh(y); assert y.status == S.WAITING
    assert ActivityLog.query.filter_by(action="status", entity_type="appointment").count() == 4


def test_cannot_finish_a_future_appointment(auth_client):
    c = mk_client(); x = mk_appt(c, at(5, 10), status=S.CONFIRMED)
    r = auth_client.post(f"/agenda/{x.id}/realizar", follow_redirects=True)
    assert "depois do início" in r.get_data(as_text=True)
    db.session.refresh(x); assert x.status == S.CONFIRMED


@pytest.mark.parametrize("start,action", [
    (S.DONE, "cancelar"), (S.DONE, "confirmar"), (S.DONE, "reativar"), (S.RESCHEDULED, "confirmar"), (S.RESCHEDULED, "reativar"),
    (S.CANCELED, "confirmar"), (S.CANCELED, "realizar"), (S.CONFIRMED, "confirmar"), (S.CONFIRMED, "reativar"), (S.WAITING, "reativar"),
])
def test_invalid_transitions_are_blocked(auth_client, start, action):
    c = mk_client(); x = mk_appt(c, at(-1, 10), status=start)
    assert act(auth_client, x, action).status_code == 302
    db.session.refresh(x); assert x.status == start


def test_reactivate_is_blocked_if_slot_was_taken(auth_client):
    a, b = mk_client("Ana"), mk_client("Bia"); x = mk_appt(a, at(10, 10), status=S.CANCELED); mk_appt(b, at(10, 10))
    r = auth_client.post(f"/agenda/{x.id}/reativar", follow_redirects=True)
    assert "Conflito" in r.get_data(as_text=True)
    db.session.refresh(x); assert x.status == S.CANCELED


def test_transitions_require_post(auth_client):
    c = mk_client(); x = mk_appt(c)
    for action in ("confirmar", "realizar", "cancelar", "reativar"):
        assert auth_client.get(f"/agenda/{x.id}/{action}").status_code == 405


def test_detail_actions_per_status(auth_client):
    c = mk_client()
    expect = {S.WAITING: "Confirmar atendimento", S.CONFIRMED: "Marcar como realizado", S.CANCELED: "Reativar atendimento", S.DONE: "encerrado", S.RESCHEDULED: "encerrado"}
    for st, text in expect.items():
        x = mk_appt(c, at(50 + list(expect).index(st)), status=st)
        assert text in auth_client.get(f"/agenda/{x.id}").get_data(as_text=True), st
    assert "data-confirm=" in auth_client.get(f"/agenda/{mk_appt(c, at(70)).id}").get_data(as_text=True)


# ---------- Remarcar ----------
def test_reschedule_keeps_history_and_moves_deposit(auth_client):
    c = mk_client(); p = Project(client_id=c.id, name="Floral"); db.session.add(p); db.session.flush()
    s = ProjectSession(project_id=p.id, scheduled_at=at()); db.session.add(s); db.session.flush()
    x = mk_appt(c, at(10, 10), 120, S.CONFIRMED, project_id=p.id, session_id=s.id, service="Sessão 2",
                price_cents=60000, deposit_cents=10000, notes="Trazer referência")
    r = auth_client.post(f"/agenda/{x.id}/remarcar", data={"date": at(17).date().isoformat(), "time": "15:30", "duration_minutes": 150})
    db.session.refresh(x)
    new = Appointment.query.filter(Appointment.id != x.id).one()
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/agenda/{new.id}")
    assert x.status == S.RESCHEDULED and x.deposit_cents == 0 and x.starts_at == at(10, 10)
    assert (new.status, new.starts_at, new.duration_minutes) == (S.WAITING, at(17, 15, 30), 150)
    assert (new.client_id, new.project_id, new.session_id, new.service, new.price_cents, new.deposit_cents) == (c.id, p.id, s.id, "Sessão 2", 60000, 10000)
    assert "Trazer referência" in new.notes and f"Remarcado de {at(10, 10):%d/%m/%Y %H:%M}." in new.notes
    assert sum(a.deposit_cents for a in Appointment.query.all()) == 10000            # sinal não duplica


def test_reschedule_conflict_changes_nothing(auth_client):
    a, b = mk_client("Ana"), mk_client("Bia"); x = mk_appt(a, at(10, 10), status=S.CONFIRMED, deposit_cents=5000); mk_appt(b, at(12, 9), 120)
    r = auth_client.post(f"/agenda/{x.id}/remarcar", data={"date": at(12).date().isoformat(), "time": "10:00", "duration_minutes": 60})
    assert r.status_code == 400 and "Conflito" in r.get_data(as_text=True)
    db.session.expire_all(); db.session.refresh(x)
    assert x.status == S.CONFIRMED and x.deposit_cents == 5000 and Appointment.query.count() == 2


def test_reschedule_same_time_and_closed_states_are_blocked(auth_client):
    c = mk_client(); x = mk_appt(c, at(10, 10))
    r = auth_client.post(f"/agenda/{x.id}/remarcar", data={"date": at(10).date().isoformat(), "time": "10:00", "duration_minutes": 60})
    assert r.status_code == 400 and "diferente do atual" in r.get_data(as_text=True)
    done = mk_appt(c, at(-9, 10), status=S.DONE)
    assert "Só atendimentos aguardando" in auth_client.get(f"/agenda/{done.id}/remarcar", follow_redirects=True).get_data(as_text=True)


def test_reschedule_form_is_prefilled_and_validated(auth_client):
    c = mk_client(); x = mk_appt(c, at(10, 9, 30), 75)
    html = auth_client.get(f"/agenda/{x.id}/remarcar").get_data(as_text=True)
    assert 'value="09:30"' in html and 'value="75"' in html
    assert auth_client.post(f"/agenda/{x.id}/remarcar", data={"date": "", "time": "", "duration_minutes": 5}).status_code == 400


def test_rescheduled_appears_in_client_history_and_agenda_tab(auth_client):
    c = mk_client(); x = mk_appt(c, at(10, 10), status=S.CONFIRMED)
    auth_client.post(f"/agenda/{x.id}/remarcar", data={"date": at(11).date().isoformat(), "time": "10:00", "duration_minutes": 60})
    assert "Atendimento remarcado" in auth_client.get(f"/clientes/{c.id}").get_data(as_text=True)
    tab = auth_client.get(f"/clientes/{c.id}?aba=agenda").get_data(as_text=True)
    assert f"/agenda/{x.id}" in tab and f"/agenda/novo?cliente={c.id}" in tab


def test_xss_is_escaped(auth_client):
    c = mk_client("<script>alert(1)</script>"); x = mk_appt(c, at(0, 10), service="<img src=x onerror=1>", notes="<b>n</b>")
    for path in ("/agenda/", "/agenda/?vista=dia", "/agenda/?vista=mes", f"/agenda/{x.id}", f"/agenda/{x.id}/editar"):
        h = auth_client.get(path).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in h and "<img src=x" not in h and "<b>n</b>" not in h, path


def test_overview_upcoming_uses_agenda_data(auth_client):
    c = mk_client("Marina Lopes"); mk_appt(c, at(1, 9), status=S.CONFIRMED)
    html = auth_client.get("/").get_data(as_text=True)
    assert "Marina Lopes" in html and "Amanhã" in html
