"""Dados-base OBRIGATÓRIOS do sistema (não são dados de demonstração).
Idempotente: pode ser executado várias vezes."""
from app.extensions import db
from app.models import AnamnesisTemplate, BodyRegion, Category, Service
from app.models.enums import CategoryKind, FieldType

BODY_REGIONS = [
    ("cabeca", "Cabeça"), ("pescoco", "Pescoço"), ("ombro", "Ombro"),
    ("braco", "Braço"), ("antebraco", "Antebraço"), ("mao", "Mão"),
    ("peito", "Peito"), ("abdomen", "Abdômen"), ("costas", "Costas"),
    ("quadril", "Quadril"), ("coxa", "Coxa"), ("panturrilha", "Panturrilha"),
    ("pe", "Pé"),
]

DEFAULT_CATEGORIES = {
    CategoryKind.INCOME: ["Tatuagem", "Sinal / Entrada", "Retoque", "Outros"],
    CategoryKind.EXPENSE: ["Materiais", "Aluguel", "Marketing", "Equipamentos", "Impostos", "Outros"],
    CategoryKind.INVENTORY: ["Agulhas", "Tintas", "Descartáveis", "Higienização", "Outros"],
}

DEFAULT_SERVICES = [
    ("Sessão de tatuagem", 180, 0),
    ("Retoque", 60, 0),
    ("Consulta / Orçamento", 30, 0),
]

YES_NO = ["Sim", "Não"]
DEFAULT_QUESTIONS = [  # (pergunta, tipo, opções, obrigatória)
    ("Possui alguma alergia (látex, tintas, medicamentos, anestésicos)?", FieldType.TEXTAREA, None, True),
    ("Possui alguma doença (diabetes, hepatite, HIV, hemofilia, cardiopatia)?", FieldType.TEXTAREA, None, True),
    ("Faz uso contínuo de algum medicamento?", FieldType.TEXTAREA, None, True),
    ("Está grávida ou amamentando?", FieldType.RADIO, YES_NO, True),
    ("Tem histórico de queloide ou problemas de cicatrização?", FieldType.RADIO, YES_NO, True),
    ("Consumiu álcool ou drogas nas últimas 24 horas?", FieldType.RADIO, YES_NO, True),
    ("Já fez tatuagem antes?", FieldType.RADIO, YES_NO, False),
    ("Observações de saúde que julgar importantes", FieldType.TEXTAREA, None, False),
]


def seed_base() -> dict:
    created = {"regions": 0, "categories": 0, "services": 0, "questions": 0}

    for position, (slug, name) in enumerate(BODY_REGIONS, start=1):
        if not BodyRegion.query.filter_by(slug=slug).first():
            db.session.add(BodyRegion(slug=slug, name=name, position=position))
            created["regions"] += 1

    for kind, names in DEFAULT_CATEGORIES.items():
        for name in names:
            if not Category.query.filter_by(kind=kind, name=name).first():
                db.session.add(Category(kind=kind, name=name))
                created["categories"] += 1

    for name, minutes, price in DEFAULT_SERVICES:
        if not Service.query.filter_by(name=name).first():
            db.session.add(Service(name=name, default_duration_minutes=minutes,
                                   default_price_cents=price))
            created["services"] += 1

    for position, (label, ftype, options, required) in enumerate(DEFAULT_QUESTIONS, start=1):
        if not AnamnesisTemplate.query.filter_by(label=label).first():
            db.session.add(AnamnesisTemplate(label=label, field_type=ftype, options=options, required=required, position=position))
            created["questions"] += 1

    db.session.commit()
    return created
