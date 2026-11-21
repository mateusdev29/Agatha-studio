from app.extensions import db
from app.models.base import TimestampMixin, enum_column, utcnow
from app.models.enums import ProjectStatus, SessionStatus


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    style = db.Column(db.String(60))
    body_region_id = db.Column(db.Integer, db.ForeignKey("body_regions.id"), index=True)
    size = db.Column(db.String(60))
    price_cents = db.Column(db.Integer, nullable=False, default=0)
    status = enum_column(ProjectStatus, default=ProjectStatus.QUOTE)
    notes = db.Column(db.Text)

    client = db.relationship("Client", back_populates="projects")
    body_region = db.relationship("BodyRegion")
    sessions = db.relationship(
        "ProjectSession", back_populates="project",
        cascade="all, delete-orphan", order_by="ProjectSession.scheduled_at",
    )
    references = db.relationship(
        "ProjectReference", back_populates="project", cascade="all, delete-orphan"
    )
    appointments = db.relationship("Appointment", back_populates="project")
    transactions = db.relationship("FinancialTransaction", back_populates="project")


class ProjectSession(TimestampMixin, db.Model):
    __tablename__ = "project_sessions"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=120)
    price_cents = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    status = enum_column(SessionStatus, default=SessionStatus.SCHEDULED)

    project = db.relationship("Project", back_populates="sessions")


class ProjectReference(db.Model):
    """Imagem de referência. O arquivo fica em uploads/projects/ com nome seguro."""
    __tablename__ = "project_references"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    stored_filename = db.Column(db.String(80), unique=True, nullable=False)
    original_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    project = db.relationship("Project", back_populates="references")
