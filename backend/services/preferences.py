from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..domain import (
    ApiError, CENT, MONEY_MAX, NUTRIENTS, TIME_MAX, array_value, decimal_text,
    decimal_value, id_value, int_value, object_value, text_list,
)
from ..models import Ingredient, Preference, db


def existing_ingredient_ids(ids):
    return set(db.session.scalars(select(Ingredient.id).where(Ingredient.id.in_(ids)))) if ids else set()


def get_preference(user_id):
    row = db.session.scalar(select(Preference).where(Preference.user_id == user_id))
    if row is None:
        return {"taste_preferences": [], "avoid_ingredients": [], "max_cooking_time": None, "nutrition_targets": {}}
    existing = existing_ingredient_ids(row.avoid_ingredients)
    return {
        "taste_preferences": row.taste_preferences,
        "avoid_ingredients": [value for value in row.avoid_ingredients if value in existing],
        "max_cooking_time": row.max_cooking_time,
        "nutrition_targets": row.nutrition_targets,
    }


def save_preference(user_id, payload):
    tags = text_list(payload.get("taste_preferences", []), "taste_preferences", unique=True)
    avoid = list(dict.fromkeys(
        id_value(value, "avoid_ingredients")
        for value in array_value(payload.get("avoid_ingredients", []), "avoid_ingredients")
    ))
    if existing_ingredient_ids(avoid) != set(avoid):
        raise ApiError("忌口列表中有食材不存在", field="avoid_ingredients")
    limit = payload.get("max_cooking_time")
    if limit is not None:
        limit = int_value(limit, "max_cooking_time", maximum=TIME_MAX)
    targets = payload.get("nutrition_targets")
    targets = {} if targets is None else object_value(targets, "nutrition_targets")
    if set(targets) - set(NUTRIENTS):
        raise ApiError("营养目标包含未知字段", field="nutrition_targets")
    entries = {
        "taste_preferences": tags, "avoid_ingredients": avoid, "max_cooking_time": limit,
        "nutrition_targets": {
            key: decimal_text(decimal_value(value, f"nutrition_targets.{key}", CENT, MONEY_MAX))
            for key, value in targets.items()
        },
    }
    insert = pg_insert if db.engine.dialect.name == "postgresql" else sqlite_insert
    db.session.execute(
        insert(Preference).values(user_id=user_id, **entries)
        .on_conflict_do_update(index_elements=[Preference.user_id], set_=entries)
    )
    return entries
