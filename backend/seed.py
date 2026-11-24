from sqlalchemy import select

from .models import Category, Ingredient, Recipe, db
from .services.catalog import ingredient_fields
from .services.recipes import add_recipe, validate_recipe


def seed_demo():
    categories = {(row.type, row.name): row for row in db.session.scalars(select(Category))}
    category_specs = {
        "ingredient": ("蔬菜", "蛋奶", "主食", "豆制品", "调味品"),
        "recipe": ("家常菜", "简餐", "汤品"),
    }
    new_categories = 0
    for kind, names in category_specs.items():
        for name in names:
            if (kind, name) not in categories:
                row = Category(type=kind, name=name)
                db.session.add(row)
                categories[kind, name] = row
                new_categories += 1
    db.session.flush()
    category_ids = {row.id: row for row in categories.values()}

    ingredients = {(row.category_id, row.name): row for row in db.session.scalars(select(Ingredient))}
    ingredient_specs = (
        ("番茄", "蔬菜", "g", 5), ("小白菜", "蔬菜", "g", 3),
        ("胡萝卜", "蔬菜", "g", 10), ("葱", "蔬菜", "把", 5),
        ("鸡蛋", "蛋奶", "个", 14), ("牛奶", "蛋奶", "mL", 5),
        ("米饭", "主食", "g", 1), ("面条", "主食", "g", 30),
        ("北豆腐", "豆制品", "g", 3), ("食用油", "调味品", "mL", 180),
    )
    new_ingredients = 0
    for name, category, unit, days in ingredient_specs:
        category_id = categories["ingredient", category].id
        if (category_id, name) not in ingredients:
            row = Ingredient(**ingredient_fields({
                "name": name, "category_id": category_id, "default_unit": unit, "shelf_life_days": days,
            }, category_ids))
            db.session.add(row)
            ingredients[category_id, name] = row
            new_ingredients += 1
    db.session.flush()
    ingredient_ids = {row.id: row for row in ingredients.values()}
    demo_ingredients = {
        name: ingredients[categories["ingredient", category].id, name]
        for name, category, _, _ in ingredient_specs
    }
    recipe_specs = (
        (
            "番茄炒蛋", "家常菜", 15, 2, ["鲜香", "酸甜"],
            [("番茄", 200, "g"), ("鸡蛋", 2, "个"), ("食用油", 10, "mL")],
            ["番茄切块，鸡蛋打散。", "热锅下油，炒熟鸡蛋后盛出。", "炒软番茄，再倒回鸡蛋翻匀调味。"],
        ),
        (
            "小白菜豆腐汤", "汤品", 20, 2, ["清淡", "鲜香"],
            [("小白菜", 150, "g"), ("北豆腐", 200, "g")],
            ["小白菜洗净，豆腐切小块。", "锅中水煮沸后加豆腐煮五分钟。", "加入小白菜烫熟，调味出锅。"],
        ),
        (
            "胡萝卜蛋炒饭", "简餐", 12, 1, ["鲜香"],
            [("胡萝卜", 50, "g"), ("鸡蛋", 1, "个"), ("米饭", 180, "g"), ("食用油", 8, "mL")],
            ["胡萝卜切成小丁，鸡蛋打散。", "将鸡蛋和胡萝卜依次炒熟。", "加入米饭大火翻炒，炒至米粒松散。"],
        ),
        (
            "番茄青菜面", "简餐", 18, 2, ["清淡", "酸甜"],
            [("番茄", 180, "g"), ("小白菜", 100, "g"), ("面条", 160, "g")],
            ["番茄切块炒出汁水，加水煮开。", "下入面条煮至熟软。", "加入小白菜煮熟后盛碗。"],
        ),
        (
            "牛奶蒸蛋", "家常菜", 22, 1, ["清淡"],
            [("鸡蛋", 2, "个"), ("牛奶", 160, "mL")],
            ["将牛奶与打匀的鸡蛋混合。", "过滤后倒入耐热碗，盖好。", "水开后用中小火蒸至凝固。"],
        ),
    )
    existing_recipes = {
        (category_id, name) for category_id, name in db.session.execute(select(Recipe.category_id, Recipe.name))
    }
    new_recipes = 0
    for name, category, minutes, servings, tags, quantities, steps in recipe_specs:
        category_id = categories["recipe", category].id
        if (category_id, name) in existing_recipes:
            continue
        payload = {
            "name": name, "category_id": category_id, "cuisine": "家常", "difficulty": "简单",
            "cooking_time": minutes, "servings": servings, "taste_tags": tags, "steps": steps,
            "ingredients": [
                {"ingredient_id": demo_ingredients[ingredient].id, "quantity": quantity, "unit": unit}
                for ingredient, quantity, unit in quantities
            ],
        }
        fields, lines = validate_recipe(payload, categories=category_ids, ingredients=ingredient_ids)
        add_recipe(fields, lines)
        new_recipes += 1
    return new_categories, new_ingredients, new_recipes
