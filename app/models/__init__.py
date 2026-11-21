"""Importa todos os modelos para o SQLAlchemy/Alembic enxergarem o schema completo."""
from app.models.activity import ActivityLog
from app.models.anamnesis import AnamnesisResponse, AnamnesisTemplate
from app.models.appointment import Appointment
from app.models.body_region import BodyRegion
from app.models.client import Client
from app.models.evaluation import Evaluation
from app.models.finance import FinancialTransaction
from app.models.inventory import InventoryItem, InventoryMovement
from app.models.project import Project, ProjectReference, ProjectSession
from app.models.quote import Quote
from app.models.settings import Category, Service, StudioSetting
from app.models.user import User

__all__ = [
    "ActivityLog", "AnamnesisResponse", "AnamnesisTemplate", "Appointment",
    "BodyRegion", "Category", "Client", "Evaluation", "FinancialTransaction",
    "InventoryItem", "InventoryMovement", "Project", "ProjectReference",
    "ProjectSession", "Quote", "Service", "StudioSetting", "User",
]
