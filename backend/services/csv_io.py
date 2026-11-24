import csv
import io
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..domain import ApiError, CSV_MAX_BYTES, NUTRIENTS, array_value, decimal_text, object_value, text_value
from ..models import Category, Ingredient, Recipe, RecipeIngredient, db
from .catalog import ingredient_fields
from .recipes import add_recipe, validate_recipe


HEADERS = {
    "ingredients": ("name", "category", "default_unit", "shelf_life_days"),
    "recipes": (
        "name", "category", "cuisine", "difficulty", "cooking_time", "servings", *NUTRIENTS,
        "taste_tags", "steps", "ingredients",
    ),
}
csv.field_size_limit(CSV_MAX_BYTES)


def row_error(row, field, message):
    return {"row": row, "field": field, "message": message}


def failure(errors):
    return ApiError("导入失败", data={"errors": errors})


def parse_csv(kind, file):
    raw = file.read(CSV_MAX_BYTES + 1)
    if len(raw) > CSV_MAX_BYTES:
        raise failure([row_error(1, "file", "CSV 不能超过 2 MiB")])
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise failure([row_error(1, "file", "请使用 UTF-8 编码保存 CSV")]) from None

    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    entries, errors = [], []
    row = 1
    has_header = False
    try:
        headers = next(reader, [])
        if len(headers) != len(HEADERS[kind]) or set(headers) != set(HEADERS[kind]):
            raise failure([row_error(1, "header", f"表头应包含 {', '.join(HEADERS[kind])}")])
        has_header = True
        for values in reader:
            row += 1
            if not values:
                continue
            if len(values) != len(headers):
                errors.append(row_error(row, "row", "字段数量与表头不一致"))
            else:
                entries.append((row, dict(zip(headers, values))))
    except csv.Error:
        errors.append(row_error(row + int(has_header), "row", "CSV 引号格式无效"))
    return entries, errors


def decode_array(value, field):
    try:
        return array_value(json.loads(value, parse_float=Decimal), field)
    except (ValueError, RecursionError):
        raise ApiError("请使用 JSON 数组", field=field) from None


def recipe_payload(payload, categories_by_name, ingredient_keys):
    for field in ("taste_tags", "steps", "ingredients"):
        payload[field] = decode_array(payload[field], field)
    for field in NUTRIENTS:
        payload[field] = payload[field].strip() or None
    for index, item in enumerate(payload["ingredients"]):
        prefix = f"ingredients[{index}]"
        item = object_value(item, prefix)
        name = text_value(item.get("name"), f"{prefix}.name", 100)
        category = text_value(item.get("category"), f"{prefix}.category", 50)
        category_id = categories_by_name.get(("ingredient", category))
        ingredient_id = ingredient_keys.get((category_id, name))
        if ingredient_id is None:
            raise ApiError(f"食材 {category} / {name} 不存在", field=f"{prefix}.name")
        item["ingredient_id"] = ingredient_id
    return payload


def import_csv(kind, file):
    entries, errors = parse_csv(kind, file)
    target_type = "ingredient" if kind == "ingredients" else "recipe"
    categories = {row.id: row for row in db.session.scalars(select(Category))}
    categories_by_name = {(row.type, row.name): row.id for row in categories.values()}
    ingredients = {row.id: row for row in db.session.scalars(select(Ingredient))}
    ingredient_keys = {(row.category_id, row.name): row.id for row in ingredients.values()}
    seen = set(ingredient_keys) if kind == "ingredients" else {
        (category_id, name) for category_id, name in db.session.execute(select(Recipe.category_id, Recipe.name))
    }
    validated = []
    for number, payload in entries:
        try:
            category_name = text_value(payload["category"], "category", 50)
            category_id = categories_by_name.get((target_type, category_name))
            if category_id is None:
                raise ApiError(f"分类 {category_name} 不存在", field="category")
            payload["category_id"] = category_id
            if kind == "ingredients":
                fields, lines = ingredient_fields(payload, categories), None
            else:
                fields, lines = validate_recipe(
                    recipe_payload(payload, categories_by_name, ingredient_keys),
                    categories=categories, ingredients=ingredients,
                )
            key = (fields["category_id"], fields["name"])
            if key in seen:
                raise ApiError("已有同名记录或在文件中重复", field="name")
            seen.add(key)
            validated.append((fields, lines))
        except ApiError as error:
            errors.append(row_error(number, error.data.get("field", "row"), str(error)))
    if errors:
        raise failure(sorted(errors, key=lambda error: error["row"]))
    if kind == "ingredients":
        db.session.add_all(Ingredient(**fields) for fields, _ in validated)
    else:
        for fields, lines in validated:
            add_recipe(fields, lines)
    return len(validated)


def encode_array(values):
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def export_csv(kind):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(HEADERS[kind])
    if kind == "ingredients":
        stmt = select(Ingredient).options(joinedload(Ingredient.category)).order_by(Ingredient.id)
        for row in db.session.scalars(stmt):
            writer.writerow((row.name, row.category.name, row.default_unit, row.shelf_life_days))
    else:
        stmt = select(Recipe).options(
            joinedload(Recipe.category),
            joinedload(Recipe.lines).joinedload(RecipeIngredient.ingredient).joinedload(Ingredient.category),
        ).order_by(Recipe.id)
        for row in db.session.scalars(stmt).unique():
            lines = [
                {"name": line.ingredient.name, "category": line.ingredient.category.name,
                 "quantity": decimal_text(line.quantity), "unit": line.unit}
                for line in row.lines
            ]
            writer.writerow((
                row.name, row.category.name, row.cuisine, row.difficulty, row.cooking_time, row.servings,
                *(decimal_text(getattr(row, key)) for key in NUTRIENTS),
                encode_array(row.taste_tags), encode_array(row.steps), encode_array(lines),
            ))
    return f"{kind}.csv", output.getvalue().encode("utf-8-sig")
