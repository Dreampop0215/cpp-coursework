from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..domain import (
    ApiError, CENT, MONEY_MAX, NUTRIENTS, TIME_MAX, array_value, choice,
    decimal_text, decimal_value, id_value, int_value, object_value, text_list, text_value,
)
from ..models import Ingredient, Recipe, RecipeIngredient, db
from .catalog import ensure_unique, valid_category_id, validate_ingredient
from .common import assign, find, keyword_filter, ordered, paginate


DIFFICULTIES = ("简单", "一般", "困难")


def recipe_view(row, *, detail=False):
    result = {
        "id": row.id, "name": row.name, "category_id": row.category_id, "category_name": row.category.name,
        "cuisine": row.cuisine, "difficulty": row.difficulty, "cooking_time": row.cooking_time,
        "servings": row.servings, "taste_tags": row.taste_tags,
        **{key: decimal_text(getattr(row, key)) for key in NUTRIENTS},
    }
    if detail:
        result["steps"] = row.steps
        result["ingredients"] = [
            {
                "id": line.id, "ingredient_id": line.ingredient_id, "ingredient_name": line.ingredient.name,
                "quantity": decimal_text(line.quantity), "unit": line.unit,
            }
            for line in row.lines
        ]
    return result


def validate_recipe(payload, *, categories=None, ingredients=None):
    fields = {
        "name": text_value(payload.get("name"), "name", 100),
        "category_id": valid_category_id(payload.get("category_id"), "recipe", categories),
        "cuisine": text_value(payload.get("cuisine"), "cuisine", 50),
        "difficulty": choice(payload.get("difficulty"), "difficulty", DIFFICULTIES),
        "cooking_time": int_value(payload.get("cooking_time"), "cooking_time", maximum=TIME_MAX),
        "servings": int_value(payload.get("servings"), "servings", minimum=1),
        "taste_tags": text_list(payload.get("taste_tags", []), "taste_tags", unique=True),
        "steps": text_list(payload.get("steps"), "steps", nonempty=True),
    }
    for key in NUTRIENTS:
        value = payload.get(key)
        fields[key] = None if value is None else decimal_value(value, key, maximum=MONEY_MAX)

    lines, ids = [], set()
    for index, line in enumerate(array_value(payload.get("ingredients"), "ingredients", nonempty=True)):
        prefix = f"ingredients[{index}]"
        line = object_value(line, prefix)
        ingredient_id = id_value(line.get("ingredient_id"), f"{prefix}.ingredient_id")
        if ingredient_id in ids:
            raise ApiError("同一道菜谱中的食材不能重复", field=f"{prefix}.ingredient_id")
        ids.add(ingredient_id)
        lines.append({
            "ingredient_id": ingredient_id, "unit": line.get("unit"),
            "quantity": decimal_value(line.get("quantity"), f"{prefix}.quantity", minimum=CENT),
        })

    if ingredients is None:
        ingredients = {
            row.id: row for row in db.session.scalars(select(Ingredient).where(Ingredient.id.in_(ids)))
        }
    for index, line in enumerate(lines):
        try:
            validate_ingredient(line["ingredient_id"], line["unit"], ingredients)
        except ApiError as error:
            raise ApiError(str(error), field=f"ingredients[{index}].{error.data['field']}") from None
    return fields, lines


def add_recipe(fields, lines):
    row = Recipe(**fields, lines=[RecipeIngredient(**line) for line in lines])
    db.session.add(row)
    return row


def save_recipe(recipe_id, payload):
    row = find(Recipe, recipe_id, lock=True) if recipe_id is not None else None
    fields, lines = validate_recipe(payload)
    ensure_unique(Recipe, {"category_id": fields["category_id"], "name": fields["name"]}, recipe_id)
    if row is None:
        row = add_recipe(fields, lines)
    else:
        row.lines.clear()
        db.session.flush()
        assign(row, fields)
        row.lines = [RecipeIngredient(**line) for line in lines]
    db.session.flush()
    return recipe_view(row, detail=True)


def get_recipes(filters, page, page_size):
    stmt = select(Recipe).options(joinedload(Recipe.category))
    stmt = keyword_filter(stmt, Recipe.name, filters)
    stmt = keyword_filter(stmt, Recipe.cuisine, filters, key="cuisine")
    if filters.get("category_id"):
        stmt = stmt.where(Recipe.category_id == id_value(filters["category_id"], "category_id"))
    if filters.get("max_cooking_time") not in (None, ""):
        limit = int_value(filters["max_cooking_time"], "max_cooking_time", maximum=TIME_MAX)
        stmt = stmt.where(Recipe.cooking_time <= limit)
    stmt = ordered(stmt, filters, Recipe.name, Recipe.id)
    return paginate(stmt, page, page_size, recipe_view)


def load_requirements(recipe_ids=None, *, time_limit=None):
    stmt = select(Recipe).options(
        joinedload(Recipe.category), joinedload(Recipe.lines).joinedload(RecipeIngredient.ingredient),
    )
    if recipe_ids is not None:
        stmt = stmt.where(Recipe.id.in_(recipe_ids))
    if time_limit is not None:
        stmt = stmt.where(Recipe.cooking_time <= time_limit)
    return list(db.session.scalars(stmt.order_by(Recipe.id)).unique())


def get_recipe(recipe_id):
    rows = load_requirements([recipe_id])
    if not rows:
        raise ApiError("记录不存在", 404)
    return recipe_view(rows[0], detail=True)
