"""Enums de domínio. Cada membro tem (valor gravado no banco, rótulo em pt-BR)."""
import enum


class LabeledEnum(str, enum.Enum):
    def __new__(cls, value, label):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj

    @classmethod
    def choices(cls):
        return [(m.value, m.label) for m in cls]


class AppointmentStatus(LabeledEnum):
    WAITING = ("aguardando", "Aguardando")
    CONFIRMED = ("confirmado", "Confirmado")
    DONE = ("realizado", "Realizado")
    CANCELED = ("cancelado", "Cancelado")
    RESCHEDULED = ("remarcado", "Remarcado")


class ProjectStatus(LabeledEnum):
    QUOTE = ("orcamento", "Orçamento")
    APPROVED = ("aprovado", "Aprovado")
    IN_PROGRESS = ("em_andamento", "Em andamento")
    DONE = ("concluido", "Concluído")
    CANCELED = ("cancelado", "Cancelado")


class SessionStatus(LabeledEnum):
    SCHEDULED = ("agendada", "Agendada")
    DONE = ("realizada", "Realizada")
    CANCELED = ("cancelada", "Cancelada")


class QuoteStatus(LabeledEnum):
    DRAFT = ("rascunho", "Rascunho")
    SENT = ("enviado", "Enviado")
    WAITING = ("aguardando_resposta", "Aguardando resposta")
    APPROVED = ("aprovado", "Aprovado")
    REJECTED = ("recusado", "Recusado")
    EXPIRED = ("expirado", "Expirado")


class FieldType(LabeledEnum):
    TEXT = ("texto", "Texto curto")
    TEXTAREA = ("textarea", "Texto longo")
    CHECKBOX = ("checkbox", "Caixas de seleção")
    RADIO = ("radio", "Escolha única")
    SELECT = ("select", "Lista suspensa")
    DATE = ("data", "Data")


class MovementType(LabeledEnum):
    IN = ("entrada", "Entrada")
    OUT = ("saida", "Saída")
    ADJUSTMENT = ("ajuste", "Ajuste")


class TransactionType(LabeledEnum):
    INCOME = ("receita", "Receita")
    EXPENSE = ("despesa", "Despesa")


class TransactionStatus(LabeledEnum):
    PENDING = ("pendente", "Pendente")
    PAID = ("pago", "Pago")
    CANCELED = ("cancelado", "Cancelado")


class PaymentMethod(LabeledEnum):
    PIX = ("pix", "Pix")
    CASH = ("dinheiro", "Dinheiro")
    CARD = ("cartao", "Cartão")
    TRANSFER = ("transferencia", "Transferência")
    OTHER = ("outros", "Outros")


class CategoryKind(LabeledEnum):
    INCOME = ("receita", "Receita")
    EXPENSE = ("despesa", "Despesa")
    INVENTORY = ("estoque", "Estoque")
