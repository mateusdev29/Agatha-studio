from app.extensions import db
from app.models import ActivityLog


def log_activity(action, description, user=None, entity_type=None, entity_id=None):
    """Adiciona um registro à sessão (o commit fica com quem chama)."""
    db.session.add(ActivityLog(
        user_id=getattr(user, "id", None),
        action=action,
        description=description[:250],
        entity_type=entity_type,
        entity_id=entity_id,
    ))
