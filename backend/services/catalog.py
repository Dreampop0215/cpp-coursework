from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..domain import ApiError, UNITS, choice, id_value, int_value, same_dimension, text_value
from ..models import Category, Ingredient, Inventory, Recipe, RecipeIngredient, ShoppingListItem, WasteLog, db
from .common import assign, find, keyword_filter, ordered, paginate


CATEGORY_TYPES = ("ingredient", "recipe")


def category_view(row):
    return {"id": row.id, "name": row.name, "type": row.type}


def ingredient_view(row):
    return {
        "id": row.id, "name": row.name, "category_id": row.category_id,
        "category_name": row.category.name, "default_unit": row.default_unit,
        "shelf_life_days": row.shelf_life_days,
    }


def valid_category_id(value, kind, categories=None):
    category_id = id_value(value, "category_id")
    category = db.session.get(Category, category_id) if categories is None else categories.get(category_id)
    if category is None or category.type != kind:
        raise ApiError("请选择对应类型的分类", field="category_id")
    return category_id


def ensure_unique(model, fields, record_id=None):
    stmt = select(model.id).filter_by(**fields)
    if record_id is not None:
        stmt = stmt.where(model.id != record_id)
    if db.session.scalar(stmt.limit(1)) is not None:
        raise ApiError("已有同名记录", field="name")


def get_categories(filters, page, page_size):
    stmt = keyword_filter(select(Category), Category.name, filters)
    if filters.get("type"):
        stmt = stmt.where(Category.type == choice(filters["type"], "type", CATEGORY_TYPES))
    stmt = ordered(stmt, filters, Category.name, Category.id)
    return paginate(stmt, page, page_size, category_view)


def get_ingredients(filters, page, page_size):
    stmt = keyword_filter(select(Ingredient).options(joinedload(Ingredient.category)), Ingredient.name, filters)
    if filters.get("category_id"):
        stmt = stmt.where(Ingredient.category_id == id_value(filters["category_id"], "category_id"))
    stmt = ordered(stmt, filters, Ingredient.name, Ingredient.id)
    return paginate(stmt, page, page_size, ingredient_view)


def save_category(category_id, payload):
    row = find(Category, category_id, lock=True) if category_id is not None else Category()
    name = text_value(payload.get("name"), "name", 50)
    kind = choice(payload.get("type", row.type), "type", CATEGORY_TYPES)
    if row.id is not None and row.type != kind:
        raise ApiError("分类创建后不能修改类型", field="type")
    ensure_unique(Category, {"type": kind, "name": name}, row.id)
    row.name, row.type = name, kind
    db.session.add(row)
    db.session.flush()
    return category_view(row)


def ingredient_fields(payload, categories=None):
    return {
        "name": text_value(payload.get("name"), "name", 100),
        "category_id": valid_category_id(payload.get("category_id"), "ingredient", categories),
        "default_unit": choice(payload.get("default_unit"), "default_unit", UNITS),
        "shelf_life_days": int_value(payload.get("shelf_life_days"), "shelf_life_days"),
    }


def save_ingredient(ingredient_id, payload):
    row = find(Ingredient, ingredient_id, lock=True) if ingredient_id is not None else Ingredient()
    fields = ingredient_fields(payload)
    if row.id is not None and not same_dimension(row.default_unit, fields["default_unit"]):
        raise ApiError("默认单位须保持原来的量纲", field="default_unit")
    ensure_unique(Ingredient, {"category_id": fields["category_id"], "name": fields["name"]}, row.id)
    db.session.add(assign(row, fields))
    db.session.flush()
    return ingredient_view(row)


def validate_ingredient(ingredient_id, unit, ingredients=None):
    ingredient = (
        db.session.get(Ingredient, ingredient_id) if ingredients is None else ingredients.get(ingredient_id)
    )
    if ingredient is None:
        raise ApiError("食材不存在", field="ingredient_id")
    choice(unit, "unit", UNITS)
    if not same_dimension(unit, ingredient.default_unit):
        raise ApiError(f"单位须与 {ingredient.name} 的默认单位 {ingredient.default_unit} 兼容", field="unit")
    return ingredient


def delete_catalog(kind, record_id):
    if kind == "categories":
        row = find(Category, record_id, lock=True)
        references = (Ingredient.category_id, Recipe.category_id)
    else:
        row = find(Ingredient, record_id, lock=True)
        references = (
            Inventory.ingredient_id, RecipeIngredient.ingredient_id,
            ShoppingListItem.ingredient_id, WasteLog.ingredient_id,
        )
    for column in references:
        if db.session.scalar(select(column).where(column == record_id).limit(1)) is not None:
            raise ApiError("记录正在被引用，无法删除")
    db.session.delete(row)
