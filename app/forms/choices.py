"""Listas de opções compartilhadas por Projetos, Orçamentos e (depois) Dashboard."""
from app.extensions import db
from app.models import BodyRegion, Client

STYLE_CHOICES = [
    ("", "Não definido"), ("Fine line", "Fine line"), ("Blackwork", "Blackwork"), ("Realismo", "Realismo"),
    ("Old school", "Old school"), ("Neotradicional", "Neotradicional"), ("Aquarela", "Aquarela"),
    ("Geométrico", "Geométrico"), ("Pontilhismo", "Pontilhismo"), ("Lettering", "Lettering"),
    ("Cobertura", "Cobertura"), ("Outro", "Outro"),
]
STYLE_VALUES = [v for v, _ in STYLE_CHOICES if v]


def body_region_choices():
    """[(id, nome)] com opção vazia. Consulta o banco a cada uso (as regiões são dado semeado)."""
    regions = BodyRegion.query.order_by(BodyRegion.position).all()
    return [(0, "Não definida")] + [(r.id, r.name) for r in regions]


def client_choices(current_client_id=None):
    """[(id, nome)] de clientes ativos; na edição mantém o cliente atual mesmo se arquivado."""
    clients = Client.query.filter(Client.archived_at.is_(None)).order_by(Client.name).all()
    if current_client_id and all(c.id != current_client_id for c in clients):
        current = db.session.get(Client, current_client_id)
        if current:
            clients.append(current)
    return [(c.id, c.name) for c in clients]
