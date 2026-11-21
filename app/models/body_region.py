from app.extensions import db


class BodyRegion(db.Model):
    """Dado de referência (semeado por `flask seed-base`)."""
    __tablename__ = "body_regions"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(60), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
