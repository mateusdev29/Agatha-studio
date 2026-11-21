import pytest

from app.extensions import db
from app.models import (Appointment, Client, Evaluation, FinancialTransaction, InventoryItem, Project, Quote,
                        StudioSetting)
from app.models.enums import AppointmentStatus as A
from app.seeds.demo import MARK, AlreadySeeded, seed_demo
from app.services.appointment_service import BLOCKING


def test_seed_creates_the_documented_amounts_and_is_marked(app):
    seed_demo()
    assert (Client.query.count(), Project.query.count(), Appointment.query.count(), Quote.query.count()) == (5, 5, 8, 5)
    assert Evaluation.query.count() == 3 and InventoryItem.query.count() == 5 and FinancialTransaction.query.count() == 8
    assert all(c.notes == MARK for c in Client.query.all())            # claramente indicado como demonstração
    assert db.session.get(StudioSetting, "demo_data") is not None


def test_seed_refuses_to_run_twice(app):
    seed_demo()
    with pytest.raises(AlreadySeeded):
        seed_demo()
    assert Client.query.count() == 5


def test_demo_agenda_has_no_overlaps(app):
    seed_demo()
    active = sorted(Appointment.query.filter(Appointment.status.in_(BLOCKING)).all(), key=lambda a: a.starts_at)
    for first, second in zip(active, active[1:]):
        assert first.ends_at <= second.starts_at, (first.starts_at, second.starts_at)


def test_demo_data_feeds_notifications_and_overview(app, auth_client):
    seed_demo()
    html = auth_client.get("/").get_data(as_text=True)
    assert "Beatriz Nunes" in html and "Amanhã" in html and "Estoque baixo" in html     # amanhã: independe da hora do teste


def test_cli_command_works_in_testing_and_is_blocked_in_production(app, monkeypatch):
    runner = app.test_cli_runner()
    assert "DEMONSTRAÇÃO" in runner.invoke(args=["seed-demo"]).output
    assert "já foram criados" in runner.invoke(args=["seed-demo"]).output
    app.config["APP_ENV"] = "production"
    assert "bloqueado" in runner.invoke(args=["seed-demo"]).output
