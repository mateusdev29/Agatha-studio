from datetime import date, datetime

from app.extensions import db
from app.models import (Appointment, BodyRegion, Category, Client, Evaluation,
                        FinancialTransaction, InventoryItem, InventoryMovement,
                        Project, ProjectSession, Quote)
from app.models.enums import (AppointmentStatus, CategoryKind, MovementType,
                              ProjectStatus, TransactionType)
from app.services.seed_base import seed_base


def test_seed_base_is_idempotent(app):
    first_regions = BodyRegion.query.count()
    seed_base()
    assert BodyRegion.query.count() == first_regions == 13
    assert Category.query.filter_by(kind=CategoryKind.INVENTORY).count() >= 1


def test_relationships_end_to_end(app):
    region = BodyRegion.query.filter_by(slug="antebraco").one()
    client = Client(name="Cliente Teste")
    db.session.add(client)
    db.session.flush()

    project = Project(client_id=client.id, name="Floral", body_region_id=region.id, price_cents=120000)
    project.sessions.append(ProjectSession(scheduled_at=datetime(2026, 10, 1, 14), price_cents=60000))
    db.session.add(project)
    db.session.flush()

    appt = Appointment(client_id=client.id, project_id=project.id,
                       starts_at=datetime(2026, 10, 1, 14), duration_minutes=90)
    quote = Quote(client_id=client.id, description="Floral no antebraço", project_id=project.id)
    tx = FinancialTransaction(type=TransactionType.INCOME, description="Sinal", amount_cents=30000,
                              date=date(2026, 10, 1), client_id=client.id, project_id=project.id)
    db.session.add_all([appt, quote, tx])
    db.session.commit()

    assert project.status == ProjectStatus.QUOTE           # padrão
    assert appt.status == AppointmentStatus.WAITING        # padrão
    assert appt.ends_at == datetime(2026, 10, 1, 15, 30)
    assert project.quote is quote
    assert client.projects.count() == 1
    assert project.body_region.name == "Antebraço"


def test_enum_stored_as_value_not_name(app):
    client = Client(name="X")
    db.session.add(client)
    db.session.flush()
    db.session.add(Project(client_id=client.id, name="P", status=ProjectStatus.IN_PROGRESS))
    db.session.commit()
    raw = db.session.execute(db.text("select status from projects")).scalar()
    assert raw == "em_andamento"


def test_evaluation_score_constraint(app):
    import pytest
    from sqlalchemy.exc import IntegrityError
    client = Client(name="Y")
    db.session.add(client)
    db.session.flush()
    db.session.add(Evaluation(client_id=client.id, score=11, evaluated_on=date.today()))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_inventory_low_stock_flag(app):
    item = InventoryItem(name="Agulha 7RL", quantity=3, min_quantity=5)
    db.session.add(item)
    db.session.flush()
    db.session.add(InventoryMovement(item_id=item.id, type=MovementType.IN, delta=3, balance_after=3))
    db.session.commit()
    assert item.is_low is True
    item.quantity = 10
    assert item.is_low is False
