from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy import case, func, select
from sqlalchemy.orm import contains_eager

from ..domain import (
    ApiError, STOCK_STATES, base_quantity, choice, date_range, date_value,
    decimal_text, decimal_value, expiry_cutoff, id_value, int_value,
)
from ..models import Category, Ingredient, Inventory, WasteLog, db
from .catalog import validate_ingredient
from .common import assign, find, keyword_filter, ordered, paginate


@dataclass
class StockAmount:
    total: Decimal = Decimal(0)
    expiring: Decimal = Decimal(0)


def expiry_state(expiry_date, today, threshold):
    days_left = (expiry_date - today).days
    if days_left < 0:
        return days_left, "expired"
    return days_left, "expiring" if days_left <= threshold else "fresh"


def batch_view(batch, today):
    days_left, status = expiry_state(batch.expiry_date, today, current_app.config["EXPIRY_WARNING_DAYS"])
    return {
        "id": batch.id, "ingredient_id": batch.ingredient_id,
        "ingredient_name": batch.ingredient.name, "category_id": batch.ingredient.category_id,
        "category_name": batch.ingredient.category.name,
        "quantity": decimal_text(batch.quantity), "unit": batch.unit,
        "purchase_date": batch.purchase_date.isoformat(), "expiry_date": batch.expiry_date.isoformat(),
        "shelf_life_days": batch.shelf_life_days, "days_left": days_left, "status": status,
    }


def lock_batch(user_id, batch_id):
    return find(Inventory, batch_id, user_id=user_id, lock=True)


def save_batch(user_id, batch_id, payload, today):
    batch = lock_batch(user_id, batch_id) if batch_id is not None else Inventory(user_id=user_id)
    ingredient_id = id_value(payload.get("ingredient_id", batch.ingredient_id), "ingredient_id")
    if batch_id is not None and ingredient_id != batch.ingredient_id:
        raise ApiError("批次创建后不能更换食材", field="ingredient_id")
    unit = payload.get("unit")
    ingredient = validate_ingredient(ingredient_id, unit)
    quantity = decimal_value(payload.get("quantity"), "quantity")
    purchase = date_value(payload.get("purchase_date"), "purchase_date")
    if purchase > today:
        raise ApiError("购买日期不能晚于今天", field="purchase_date")
    if batch_id is not None and purchase != batch.purchase_date:
        earlier_waste = select(WasteLog.id).where(
            WasteLog.inventory_id == batch.id, WasteLog.waste_date < purchase,
        ).limit(1)
        if db.session.scalar(earlier_waste) is not None:
            raise ApiError("购买日期不能晚于该批次已登记的浪费日期", field="purchase_date")

    expiry, shelf_life = payload.get("expiry_date"), payload.get("shelf_life_days")
    if shelf_life is not None:
        shelf_life = int_value(shelf_life, "shelf_life_days")
    if expiry is not None:
        expiry = date_value(expiry, "expiry_date")
        days = (expiry - purchase).days
        if days < 0:
            raise ApiError("到期日不能早于购买日", field="expiry_date")
        if shelf_life is not None and shelf_life != days:
            raise ApiError("保质期与到期日不一致", field="expiry_date")
        shelf_life = days
    else:
        if shelf_life is None:
            shelf_life = batch.shelf_life_days if batch_id is not None else ingredient.shelf_life_days
        if shelf_life > (purchase.max - purchase).days:
            raise ApiError("到期日期超出范围", field="shelf_life_days")
        expiry = purchase + timedelta(days=shelf_life)

    assign(batch, {
        "ingredient": ingredient, "quantity": quantity, "unit": unit,
        "purchase_date": purchase, "expiry_date": expiry, "shelf_life_days": shelf_life,
    })
    db.session.add(batch)
    db.session.flush()
    return batch_view(batch, today)


def batch_query(user_id):
    return (
        select(Inventory).join(Inventory.ingredient).join(Ingredient.category)
        .options(contains_eager(Inventory.ingredient).contains_eager(Ingredient.category))
        .where(Inventory.user_id == user_id).order_by(Inventory.expiry_date, Inventory.id)
    )


def expiring_batches(user_id, today, category_id=None):
    stmt = batch_query(user_id).where(
        Inventory.quantity > 0, Inventory.expiry_date.between(today, expiry_cutoff(today)),
    )
    if category_id is not None:
        stmt = stmt.where(Category.id == category_id)
    return stmt


def get_batches(user_id, filters, page, page_size, today, expiring=False):
    stmt = expiring_batches(user_id, today) if expiring else batch_query(user_id)
    stmt = keyword_filter(stmt, Ingredient.name, filters)
    if filters.get("category_id"):
        stmt = stmt.where(Ingredient.category_id == id_value(filters["category_id"], "category_id"))
    if filters.get("ingredient_id"):
        stmt = stmt.where(Inventory.ingredient_id == id_value(filters["ingredient_id"], "ingredient_id"))
    if filters.get("status") and not expiring:
        status = choice(filters["status"], "status", STOCK_STATES)
        conditions = {
            "expired": Inventory.expiry_date < today,
            "expiring": Inventory.expiry_date.between(today, expiry_cutoff(today)),
            "fresh": Inventory.expiry_date > expiry_cutoff(today),
        }
        stmt = stmt.where(conditions[status])
    start, end = date_range(filters)
    if start:
        stmt = stmt.where(Inventory.expiry_date >= start)
    if end:
        stmt = stmt.where(Inventory.expiry_date <= end)
    stmt = ordered(stmt, filters, Inventory.expiry_date, Inventory.id)
    return paginate(stmt, page, page_size, lambda row: batch_view(row, today))


def delete_batch(user_id, batch_id):
    batch = lock_batch(user_id, batch_id)
    if db.session.scalar(select(WasteLog.id).where(WasteLog.inventory_id == batch.id).limit(1)) is not None:
        raise ApiError("此批次已有浪费记录，无法删除")
    db.session.delete(batch)


def active_stock(user_id, today):
    stmt = (
        select(
            Inventory.ingredient_id, Inventory.unit, func.sum(Inventory.quantity),
            func.sum(case((Inventory.expiry_date <= expiry_cutoff(today), Inventory.quantity), else_=0)),
        )
        .where(Inventory.user_id == user_id, Inventory.quantity > 0, Inventory.expiry_date >= today)
        .group_by(Inventory.ingredient_id, Inventory.unit)
    )
    stock = {}
    for ingredient_id, unit, total, expiring in db.session.execute(stmt):
        amount = stock.setdefault(ingredient_id, StockAmount())
        amount.total += base_quantity(total, unit)
        amount.expiring += base_quantity(expiring, unit)
    return stock
