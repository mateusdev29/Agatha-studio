"""Sinal do atendimento lançado no Financeiro.

Regras: no máximo UM lançamento de sinal por atendimento (trava também no banco); depois de lançado, o Financeiro é a
fonte da verdade do valor; remarcar leva o lançamento junto; cancelar NUNCA mexe no dinheiro sozinho.
"""
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment, Category, FinancialTransaction as T
from app.models.enums import AppointmentStatus as S, CategoryKind, TransactionType
from app.services.activity_service import log_activity

DEPOSIT_CATEGORY = "Sinal / Entrada"


class DepositError(Exception):
    """Regra violada; a mensagem é segura para mostrar à usuária."""


def deposit_transaction(appt: Appointment) -> T | None:
    return T.query.filter_by(appointment_id=appt.id, is_deposit=True).first()


def _category_id() -> int | None:
    cat = Category.query.filter_by(kind=CategoryKind.INCOME, name=DEPOSIT_CATEGORY, is_active=True).first()
    return cat.id if cat else None          # categoria renomeada/desativada em Configurações: lança sem categoria


def launch_deposit(appt: Appointment, method, when, status, user) -> T:
    if appt.status in (S.CANCELED, S.RESCHEDULED):
        raise DepositError("Não é possível lançar o sinal de um atendimento cancelado ou remarcado.")
    if not appt.deposit_cents or appt.deposit_cents <= 0:
        raise DepositError("Este atendimento não tem sinal combinado. Edite o atendimento e informe o valor do sinal.")
    if deposit_transaction(appt):
        raise DepositError("O sinal deste atendimento já foi lançado no Financeiro.")

    t = T(type=TransactionType.INCOME, description=f"Sinal: {appt.service or 'Atendimento'}", category_id=_category_id(),
          amount_cents=appt.deposit_cents, date=when, client_id=appt.client_id, project_id=appt.project_id,
          appointment_id=appt.id, is_deposit=True, payment_method=method, status=status)
    try:
        db.session.add(t)
        db.session.flush()
        log_activity("created", f"Sinal lançado no Financeiro: {appt.client.name}", user, "transaction", t.id)
        db.session.commit()
    except IntegrityError:                        # dois cliques/abas ao mesmo tempo: a trava do banco vence
        db.session.rollback()
        raise DepositError("O sinal deste atendimento já foi lançado no Financeiro.")
    return t


def move_deposit(old: Appointment, new: Appointment) -> None:
    """Remarcação: o lançamento acompanha o novo atendimento (sem commit; roda dentro da transação do chamador)."""
    t = deposit_transaction(old)
    if t:
        t.appointment_id = new.id
