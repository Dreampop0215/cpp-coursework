from decimal import Decimal
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..domain import (
    ApiError, CENT, QTY_MAX, array_value, base_quantity, ceil_quantity, choice,
    decimal_text, decimal_value, id_value, int_value, object_value, text_value,
)
from ..models import ShoppingList, ShoppingListItem, db
from .catalog import validate_ingredient
from .common import assign, find, paginate, timestamp_text
from .inventory import StockAmount, active_stock
from .recipes import load_requirements


def item_view(item):
    return {
        "id": item.id, "ingredient_id": item.ingredient_id, "ingredient_name": item.ingredient.name,
        "quantity": decimal_text(item.quantity), "unit": item.unit, "is_checked": item.is_checked,
    }


def list_view(row, *, detail=False):
    result = {"id": row.id, "name": row.name, "status": row.status, "created_at": timestamp_text(row.created_at)}
    if detail:
        result["items"] = [item_view(item) for item in row.items]
    return result


def get_list(user_id, list_id):
    stmt = (
        select(ShoppingList)
        .options(joinedload(ShoppingList.items).joinedload(ShoppingListItem.ingredient))
        .where(ShoppingList.id == list_id, ShoppingList.user_id == user_id)
    )
    row = db.session.scalars(stmt).unique().one_or_none()
    if row is None:
        raise ApiError("记录不存在", 404)
    return list_view(row, detail=True)


def get_lists(user_id, filters, page, page_size):
    stmt = select(ShoppingList).where(ShoppingList.user_id == user_id)
    if filters.get("status"):
        stmt = stmt.where(ShoppingList.status == choice(filters["status"], "status", ("open", "completed")))
    stmt = stmt.order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
    return paginate(stmt, page, page_size, list_view)


def save_list(user_id, list_id, payload):
    row = find(ShoppingList, list_id, user_id=user_id, lock=True) if list_id is not None else ShoppingList(user_id=user_id)
    row.name = text_value(payload.get("name"), "name", 100)
    db.session.add(row)
    db.session.flush()
    return get_list(user_id, row.id)


def merge_needs(selections, recipe_details):
    needs = {}
    for recipe in recipe_details:
        ratio = Fraction(selections[recipe.id], recipe.servings)
        for line in recipe.lines:
            previous, _ = needs.get(line.ingredient_id, (Fraction(0), line.ingredient))
            needs[line.ingredient_id] = (previous + Fraction(base_quantity(line.quantity, line.unit)) * ratio, line.ingredient)
    return needs


def generate_list(user_id, payload, today):
    name = text_value(payload.get("name"), "name", 100)
    selections = {}
    for index, selection in enumerate(array_value(payload.get("recipes"), "recipes", nonempty=True)):
        prefix = f"recipes[{index}]"
        selection = object_value(selection, prefix)
        recipe_id = id_value(selection.get("recipe_id"), f"{prefix}.recipe_id")
        if recipe_id in selections:
            raise ApiError("同一份清单不能重复选择菜谱", field=f"{prefix}.recipe_id")
        selections[recipe_id] = int_value(selection.get("servings"), f"{prefix}.servings", minimum=1)

    recipes = load_requirements(list(selections))
    if len(recipes) != len(selections):
        raise ApiError("所选菜谱中有记录不存在", field="recipes")
    stock = active_stock(user_id, today)
    items = []
    for ingredient_id, (needed, ingredient) in sorted(merge_needs(selections, recipes).items()):
        gap = needed - Fraction(stock.get(ingredient_id, StockAmount()).total)
        if gap > 0:
            quantity = ceil_quantity(gap, ingredient.default_unit)
            if quantity > QTY_MAX:
                raise ApiError(f"{ingredient.name}的采购量超过 {QTY_MAX}", field="recipes")
            items.append(ShoppingListItem(ingredient=ingredient, quantity=quantity, unit=ingredient.default_unit))
    row = ShoppingList(user_id=user_id, name=name, items=items)
    db.session.add(row)
    db.session.flush()
    return list_view(row, detail=True)


def list_item(list_id, item_id):
    item = db.session.scalar(
        select(ShoppingListItem).where(ShoppingListItem.id == item_id, ShoppingListItem.list_id == list_id)
    )
    if item is None:
        raise ApiError("记录不存在", 404)
    return item


def update_status(row):
    checks = list(db.session.scalars(select(ShoppingListItem.is_checked).where(ShoppingListItem.list_id == row.id)))
    row.status = "completed" if checks and all(checks) else "open"
    return row.status


def update_item(user_id, list_id, item_id, payload):
    row = find(ShoppingList, list_id, user_id=user_id, lock=True)
    item = list_item(row.id, item_id) if item_id is not None else ShoppingListItem(list_id=row.id, is_checked=False)
    ingredient_id = id_value(payload.get("ingredient_id", item.ingredient_id), "ingredient_id")
    unit = payload.get("unit", item.unit)
    ingredient = validate_ingredient(ingredient_id, unit)
    quantity = decimal_value(payload.get("quantity", item.quantity), "quantity", minimum=CENT)
    is_checked = payload.get("is_checked", item.is_checked)
    if type(is_checked) is not bool:
        raise ApiError("勾选状态须为布尔值", field="is_checked")
    other = db.session.scalar(select(ShoppingListItem.id).where(
        ShoppingListItem.list_id == row.id, ShoppingListItem.ingredient_id == ingredient_id,
    ))
    if other is not None and other != item_id:
        raise ApiError("此食材已经在清单中", field="ingredient_id")
    db.session.add(assign(item, {"ingredient": ingredient, "quantity": quantity, "unit": unit, "is_checked": is_checked}))
    db.session.flush()
    return {"item": item_view(item), "status": update_status(row)}


def delete_item(user_id, list_id, item_id):
    row = find(ShoppingList, list_id, user_id=user_id, lock=True)
    db.session.delete(list_item(row.id, item_id))
    db.session.flush()
    return {"item": None, "status": update_status(row)}
