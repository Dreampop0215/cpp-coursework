from collections import defaultdict
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import contains_eager

from ..domain import (
    ApiError, CENT, MONEY_MAX, UNITS, base_quantity, choice, date_range, date_value,
    decimal_text, decimal_value, id_value, same_dimension, text_value,
)
from ..models import Category, Ingredient, WasteLog, db
from .catalog import validate_ingredient
from .common import ordered, paginate
from .inventory import lock_batch


def waste_view(row):
    return {
        "id": row.id, "inventory_id": row.inventory_id, "ingredient_id": row.ingredient_id,
        "ingredient_name": row.ingredient.name, "category_id": row.ingredient.category_id,
        "quantity": decimal_text(row.quantity), "unit": row.unit, "amount": decimal_text(row.amount),
        "reason": row.reason, "waste_date": row.waste_date.isoformat(),
    }


def record_waste(user_id, payload, today):
    ingredient_id = id_value(payload.get("ingredient_id"), "ingredient_id")
    unit = payload.get("unit")
    ingredient = validate_ingredient(ingredient_id, unit)
    quantity = decimal_value(payload.get("quantity"), "quantity", minimum=CENT)
    amount = decimal_value(payload.get("amount"), "amount", maximum=MONEY_MAX)
    reason = text_value(payload.get("reason"), "reason", 100)
    waste_date = date_value(payload.get("waste_date"), "waste_date")
    if waste_date > today:
        raise ApiError("浪费日期不能晚于今天", field="waste_date")

    inventory_id = payload.get("inventory_id")
    if inventory_id is not None:
        inventory_id = id_value(inventory_id, "inventory_id")
        batch = lock_batch(user_id, inventory_id)
        if batch.ingredient_id != ingredient_id:
            raise ApiError("浪费登记的食材须与库存批次一致", field="inventory_id")
        if waste_date < batch.purchase_date:
            raise ApiError("浪费日期不能早于该批次购买日", field="waste_date")
        if not same_dimension(unit, batch.unit):
            raise ApiError("浪费单位与库存批次的单位不兼容", field="unit")
        deduction = base_quantity(quantity, unit) / UNITS[batch.unit][1]
        if deduction != deduction.quantize(CENT):
            raise ApiError(f"换算后的浪费量须能以两位小数从批次扣减，批次单位为 {batch.unit}", field="quantity")
        if deduction > batch.quantity:
            raise ApiError("浪费数量超过该批次实存量", field="quantity")
        batch.quantity -= deduction

    record = WasteLog(
        user_id=user_id, ingredient=ingredient, inventory_id=inventory_id,
        unit=unit, quantity=quantity, amount=amount, reason=reason, waste_date=waste_date,
    )
    db.session.add(record)
    db.session.flush()
    return waste_view(record)


def apply_filters(stmt, user_id, filters):
    stmt = stmt.where(WasteLog.user_id == user_id)
    start, end = date_range(filters)
    if start:
        stmt = stmt.where(WasteLog.waste_date >= start)
    if end:
        stmt = stmt.where(WasteLog.waste_date <= end)
    if filters.get("category_id"):
        stmt = stmt.where(Ingredient.category_id == id_value(filters["category_id"], "category_id"))
    return stmt


def list_waste(user_id, filters, page, page_size):
    stmt = select(WasteLog).join(WasteLog.ingredient).options(contains_eager(WasteLog.ingredient))
    stmt = apply_filters(stmt, user_id, filters)
    stmt = ordered(stmt, filters, WasteLog.waste_date, WasteLog.id, default="desc")
    return paginate(stmt, page, page_size, waste_view)


def aggregate_waste(user_id, filters):
    group = choice(filters.get("group_by", "month"), "group_by", ("month", "category", "reason"))
    group_columns = {
        "month": (extract("year", WasteLog.waste_date), extract("month", WasteLog.waste_date)),
        "category": (Category.id, Category.name),
        "reason": (WasteLog.reason,),
    }[group]
    stmt = (
        select(*group_columns, WasteLog.unit, func.count(WasteLog.id),
               func.sum(WasteLog.quantity), func.sum(WasteLog.amount))
        .select_from(WasteLog).join(WasteLog.ingredient).join(Ingredient.category)
        .group_by(*group_columns, WasteLog.unit)
    )
    groups = {}
    for *keys, unit, count, quantity, amount in db.session.execute(apply_filters(stmt, user_id, filters)):
        if group == "month":
            key = f"{int(keys[0]):04d}-{int(keys[1]):02d}"
            label = key
        elif group == "category":
            key, label = keys
        else:
            key = label = keys[0]
        entry = groups.setdefault(key, {
            "key": key, "label": label, "count": 0, "amount": Decimal(0), "quantities": defaultdict(Decimal),
        })
        entry["count"] += count
        entry["amount"] += amount
        entry["quantities"][UNITS[unit][0]] += base_quantity(quantity, unit)
    for entry in groups.values():
        entry["amount"] = decimal_text(entry["amount"])
        entry["quantities"] = [
            {"unit": unit, "quantity": decimal_text(total)} for unit, total in sorted(entry["quantities"].items())
        ]
    return {"group_by": group, "items": sorted(groups.values(), key=lambda entry: (entry["label"], entry["key"]))}
