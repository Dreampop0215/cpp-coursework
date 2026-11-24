from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .domain import NUTRIENTS


db = SQLAlchemy()
json_type = db.JSON().with_variant(JSONB(), "postgresql")


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_categories_type_name"),
        CheckConstraint("type IN ('ingredient', 'recipe')"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)


class Ingredient(db.Model):
    __tablename__ = "ingredients"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_ingredients_category_name"),
        CheckConstraint("shelf_life_days >= 0"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.ForeignKey("categories.id"), nullable=False)
    default_unit = db.Column(db.String(20), nullable=False)
    shelf_life_days = db.Column(db.Integer, nullable=False)
    category = relationship(Category)


class Recipe(db.Model):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_recipes_category_name"),
        CheckConstraint("cooking_time BETWEEN 0 AND 1440"),
        CheckConstraint("servings > 0"),
        *(CheckConstraint(f"{field} >= 0") for field in NUTRIENTS),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.ForeignKey("categories.id"), nullable=False)
    cuisine = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    cooking_time = db.Column(db.Integer, nullable=False)
    servings = db.Column(db.Integer, nullable=False)
    calories = db.Column(db.Numeric(10, 2))
    protein = db.Column(db.Numeric(10, 2))
    fat = db.Column(db.Numeric(10, 2))
    carbohydrate = db.Column(db.Numeric(10, 2))
    taste_tags = db.Column(json_type, nullable=False)
    steps = db.Column(json_type, nullable=False)
    category = relationship(Category)
    lines = relationship(
        "RecipeIngredient", order_by="RecipeIngredient.id",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class RecipeIngredient(db.Model):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_ingredient"),
        CheckConstraint("quantity > 0 AND quantity <= 99999"),
    )

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = db.Column(db.ForeignKey("ingredients.id"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(7, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    ingredient = relationship(Ingredient)


class Inventory(db.Model):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("quantity BETWEEN 0 AND 99999"),
        CheckConstraint("shelf_life_days >= 0 AND expiry_date >= purchase_date"),
        CheckConstraint("expiry_date = purchase_date + shelf_life_days").ddl_if(dialect="postgresql"),
        Index("ix_inventory_user_expiry", "user_id", "expiry_date", "id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    ingredient_id = db.Column(db.ForeignKey("ingredients.id"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(7, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    shelf_life_days = db.Column(db.Integer, nullable=False)
    ingredient = relationship(Ingredient)


class ShoppingList(db.Model):
    __tablename__ = "shopping_list"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'completed')"),
        Index("ix_shopping_list_user_created", "user_id", "created_at", "id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", server_default="open")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    items = relationship(
        "ShoppingListItem", order_by="ShoppingListItem.id",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class ShoppingListItem(db.Model):
    __tablename__ = "shopping_list_items"
    __table_args__ = (
        UniqueConstraint("list_id", "ingredient_id", name="uq_shopping_ingredient"),
        CheckConstraint("quantity > 0 AND quantity <= 99999"),
    )

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.ForeignKey("shopping_list.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = db.Column(db.ForeignKey("ingredients.id"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    is_checked = db.Column(db.Boolean, nullable=False, default=False, server_default=false())
    ingredient = relationship(Ingredient)


class WasteLog(db.Model):
    __tablename__ = "waste_log"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <= 99999"),
        CheckConstraint("amount >= 0"),
        Index("ix_waste_user_date", "user_id", "waste_date", "id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    ingredient_id = db.Column(db.ForeignKey("ingredients.id"), nullable=False, index=True)
    inventory_id = db.Column(db.ForeignKey("inventory.id"), index=True)
    quantity = db.Column(db.Numeric(7, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    waste_date = db.Column(db.Date, nullable=False)
    ingredient = relationship(Ingredient)


class Preference(db.Model):
    __tablename__ = "preferences"
    __table_args__ = (CheckConstraint("max_cooking_time BETWEEN 0 AND 1440"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False, unique=True)
    taste_preferences = db.Column(json_type, nullable=False)
    avoid_ingredients = db.Column(json_type, nullable=False)
    max_cooking_time = db.Column(db.Integer)
    nutrition_targets = db.Column(json_type, nullable=False)
