from app.extensions import db
from app.models.base import TimestampMixin, enum_column
from app.models.enums import QuoteStatus


class Quote(TimestampMixin, db.Model):
    __tablename__ = "quotes"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    style = db.Column(db.String(60))
    body_region_id = db.Column(db.Integer, db.ForeignKey("body_regions.id"))
    size = db.Column(db.String(60))
    price_cents = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    valid_until = db.Column(db.Date)
    status = enum_column(QuoteStatus, default=QuoteStatus.DRAFT)
    # Projeto gerado a partir da aprovação (evita criar duas vezes)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    client = db.relationship("Client", back_populates="quotes")
    body_region = db.relationship("BodyRegion")
    project = db.relationship("Project", backref=db.backref("quote", uselist=False))
