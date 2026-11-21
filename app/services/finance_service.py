"""Regras do Financeiro (sem request/response). Valores em centavos, sempre positivos."""
from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Appointment, Category, Client, FinancialTransaction as T
from app.models.enums import TransactionStatus as TS, TransactionType as TT
from app.services.activity_service import log_activity

PER_PAGE = 20


def _like(term):
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(tab="todos", status="", q="", period=None, page=1):
    stmt = (db.select(T).outerjoin(Client).options(joinedload(T.category), joinedload(T.client), joinedload(T.project)))
    if tab == "receitas":
        stmt = stmt.where(T.type == TT.INCOME)
    elif tab == "despesas":
        stmt = stmt.where(T.type == TT.EXPENSE)
    elif tab == "pagamentos":
        stmt = stmt.where(T.type == TT.INCOME, T.client_id.isnot(None))
    if status in {s.value for s in TS}:
        stmt = stmt.where(T.status == TS(status))
    if period:
        stmt = stmt.where(T.date >= period.start, T.date <= period.end)
    q = (q or "").strip()
    if q:
        p = _like(q)
        stmt = stmt.where(or_(T.description.ilike(p, escape="\\"), Client.name.ilike(p, escape="\\"), T.supplier.ilike(p, escape="\\")))
    return db.paginate(stmt.order_by(T.date.desc(), T.id.desc()), page=page, per_page=PER_PAGE, error_out=False)


@dataclass
class Summary:
    income: int
    expense: int
    pending_in: int
    pending_out: int

    @property
    def profit(self):
        return self.income - self.expense


def _sum(kind, status, period):
    return db.session.query(func.coalesce(func.sum(T.amount_cents), 0)).filter(
        T.type == kind, T.status == status, T.date >= period.start, T.date <= period.end).scalar()


def summary(period) -> Summary:
    return Summary(_sum(TT.INCOME, TS.PAID, period), _sum(TT.EXPENSE, TS.PAID, period),
                   _sum(TT.INCOME, TS.PENDING, period), _sum(TT.EXPENSE, TS.PENDING, period))


def category_breakdown(period):
    """[(tipo, categoria, total)] das movimentações PAGAS no período, maiores primeiro."""
    rows = (db.session.query(T.type, func.coalesce(Category.name, "Sem categoria"), func.sum(T.amount_cents))
            .outerjoin(Category, T.category_id == Category.id)
            .filter(T.status == TS.PAID, T.date >= period.start, T.date <= period.end)
            .group_by(T.type, Category.name).all())
    return sorted(rows, key=lambda r: (r[0] != TT.INCOME, -r[2]))


def save(transaction, data: dict, user) -> T:
    creating = transaction is None
    transaction = transaction or T()
    for k, v in data.items():
        setattr(transaction, k, v)
    if transaction.is_deposit and transaction.appointment_id:      # sinal de atendimento: mantém Agenda e Financeiro iguais
        appt = db.session.get(Appointment, transaction.appointment_id)
        if appt:
            transaction.client_id, transaction.project_id = appt.client_id, appt.project_id
            appt.deposit_cents = transaction.amount_cents
    db.session.add(transaction)
    db.session.flush()
    verb = "registrada" if creating else "atualizada"
    log_activity("created" if creating else "updated",
                 f"{transaction.type.label} {verb}: {transaction.description}", user, "transaction", transaction.id)
    db.session.commit()
    return transaction


def mark_paid(transaction, user) -> None:
    if transaction.status != TS.PENDING:
        raise ValueError("Só lançamentos pendentes podem ser marcados como pagos.")
    transaction.status = TS.PAID
    log_activity("status", f"{transaction.type.label} paga: {transaction.description}", user, "transaction", transaction.id)
    db.session.commit()


def delete(transaction, user) -> None:
    log_activity("deleted", f"{transaction.type.label} excluída: {transaction.description}", user, "transaction", transaction.id)
    db.session.delete(transaction)
    db.session.commit()
