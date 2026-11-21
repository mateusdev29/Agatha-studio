"""Regras do Estoque. O saldo nunca fica negativo; cada movimentação registra delta e saldo resultante."""
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import InventoryItem as Item, InventoryMovement as Mov
from app.models.enums import MovementType as MT
from app.services.activity_service import log_activity

PER_PAGE = 20


class StockError(Exception):
    """Regra violada; mensagem segura para a usuária."""


def _like(t):
    return "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_items(q="", category_id=None, low=False, active=True, page=1):
    stmt = db.select(Item).options(joinedload(Item.category)).where(Item.is_active.is_(active))
    if category_id:
        stmt = stmt.where(Item.category_id == category_id)
    if low:
        stmt = stmt.where(Item.quantity <= Item.min_quantity)
    q = (q or "").strip()
    if q:
        p = _like(q)
        stmt = stmt.where(or_(Item.name.ilike(p, escape="\\"), Item.supplier.ilike(p, escape="\\")))
    return db.paginate(stmt.order_by(func.lower(Item.name), Item.id), page=page, per_page=PER_PAGE, error_out=False)


def search_movements(page=1, item_id=None):
    stmt = db.select(Mov).options(joinedload(Mov.item), joinedload(Mov.user))
    if item_id:
        stmt = stmt.where(Mov.item_id == item_id)
    return db.paginate(stmt.order_by(Mov.created_at.desc(), Mov.id.desc()), page=page, per_page=PER_PAGE, error_out=False)


def low_stock_count() -> int:
    return Item.query.filter(Item.is_active.is_(True), Item.quantity <= Item.min_quantity).count()


def _record(item, mtype, delta, reason, user):
    mov = Mov(item_id=item.id, type=mtype, delta=delta, balance_after=item.quantity, reason=reason or None,
              user_id=getattr(user, "id", None))
    db.session.add(mov)
    return mov


def create_item(data: dict, initial_qty: int, user) -> Item:
    item = Item(**data, quantity=0)
    db.session.add(item)
    db.session.flush()
    if initial_qty and initial_qty > 0:
        item.quantity = initial_qty
        _record(item, MT.IN, initial_qty, "Saldo inicial", user)
    log_activity("created", f"Produto cadastrado: {item.name}", user, "inventory", item.id)
    db.session.commit()
    return item


def update_item(item: Item, data: dict, user) -> Item:
    for k, v in data.items():
        setattr(item, k, v)
    log_activity("updated", f"Produto atualizado: {item.name}", user, "inventory", item.id)
    db.session.commit()
    return item


def set_active(item: Item, active: bool, user) -> None:
    item.is_active = active
    log_activity("updated", f"Produto {'restaurado' if active else 'arquivado'}: {item.name}", user, "inventory", item.id)
    db.session.commit()


def move(item: Item, mtype: MT, quantity: int, reason: str, user) -> Mov:
    """entrada soma, saída subtrai (sem ficar negativo) e ajuste define o novo saldo absoluto."""
    if not item.is_active:
        raise StockError("Restaure o produto antes de movimentar o estoque.")
    if quantity is None or quantity < 0 or (mtype != MT.ADJUSTMENT and quantity == 0):
        raise StockError("Informe uma quantidade válida.")
    if mtype == MT.IN:
        delta = quantity
    elif mtype == MT.OUT:
        if quantity > item.quantity:
            raise StockError(f"Saldo insuficiente: há {item.quantity} {item.unit} em estoque.")
        delta = -quantity
    else:
        delta = quantity - item.quantity
    try:
        item.quantity += delta
        mov = _record(item, mtype, delta, reason, user)
        log_activity("stock", f"{mtype.label} de estoque: {item.name} ({delta:+d})", user, "inventory", item.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return mov
