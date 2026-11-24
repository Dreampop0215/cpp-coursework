import json
from dataclasses import dataclass
from decimal import Decimal, Inexact, InvalidOperation, localcontext

from flask import current_app

from ..domain import ApiError, TIME_MAX, base_quantity, ceil_quantity, decimal_text, int_value
from .inventory import StockAmount, active_stock
from .preferences import get_preference
from .recipes import load_requirements


DEFAULT_WEIGHTS = {
    "expiring": Decimal("0.35"), "stock": Decimal("0.30"), "taste": Decimal("0.15"),
    "time": Decimal("0.10"), "nutrition": Decimal("0.10"),
}
EMPTY_STOCK = StockAmount()


@dataclass
class RecommendContext:
    stock: dict
    tastes: set
    time_limit: int | None
    nutrition_targets: dict


def options_from(values):
    top_n = int_value(values.get("top_n", 5), "top_n", 1, 20)
    limit = values.get("max_cooking_time")
    if limit not in (None, ""):
        limit = int_value(limit, "max_cooking_time", maximum=TIME_MAX)
    else:
        limit = None

    raw_weights = values.get("weights")
    if raw_weights is None:
        return top_n, limit, DEFAULT_WEIGHTS
    try:
        if isinstance(raw_weights, str):
            raw_weights = json.loads(raw_weights, parse_float=Decimal, parse_int=Decimal)
        if not isinstance(raw_weights, dict) or set(raw_weights) != set(DEFAULT_WEIGHTS):
            raise ValueError
        weights = {key: Decimal(str(raw_weights[key])) for key in DEFAULT_WEIGHTS}
        if any(not weight.is_finite() or not 0 <= weight <= 1 for weight in weights.values()):
            raise ValueError
        with localcontext() as arithmetic:
            arithmetic.prec = 2 + sum(len(weight.as_tuple().digits) for weight in weights.values())
            arithmetic.traps[Inexact] = True
            if sum(weights.values()) != 1:
                raise ValueError
    except (Inexact, InvalidOperation, ValueError, TypeError, RecursionError):
        raise ApiError("请提供全部五项非负权重，权重之和须为 1", field="weights") from None
    return top_n, limit, weights


def coverage(recipe, context, attr):
    fractions = [
        min(Decimal(1), getattr(context.stock.get(line.ingredient_id, EMPTY_STOCK), attr)
            / base_quantity(line.quantity, line.unit))
        for line in recipe.lines
    ]
    # A consistent summation order keeps Decimal rounding independent of recipe line order.
    return sum(sorted(fractions)) * 100 / len(fractions)


def expiring_score(recipe, context):
    return coverage(recipe, context, "expiring")


def stock_score(recipe, context):
    return coverage(recipe, context, "total")


def taste_score(recipe, context):
    if not context.tastes:
        return Decimal(50)
    return Decimal(100) * len(context.tastes.intersection(recipe.taste_tags)) / len(context.tastes)


def time_score(recipe, context):
    if context.time_limit is None:
        return Decimal(50)
    if context.time_limit == 0:
        return Decimal(100)
    return Decimal(100) * (context.time_limit - recipe.cooking_time) / context.time_limit


def nutrition_score(recipe, context):
    if not context.nutrition_targets:
        return Decimal(50)
    scores = []
    for key, target in context.nutrition_targets.items():
        actual = getattr(recipe, key)
        scores.append(Decimal(0) if actual is None else max(Decimal(0), 1 - abs(actual - target) / target))
    return sum(scores) * 100 / len(scores)


SCORERS = {
    "expiring": expiring_score, "stock": stock_score, "taste": taste_score,
    "time": time_score, "nutrition": nutrition_score,
}


def expiring_hits(recipe, context):
    return [
        line.ingredient.name for line in recipe.lines
        if context.stock.get(line.ingredient_id, EMPTY_STOCK).expiring > 0
    ]


def recommendation_view(recipe, context, total=None, details=None):
    hits = expiring_hits(recipe, context)
    reasons = [f"可利用临期食材：{'、'.join(hits)}"] if hits else []
    missing = []
    for line in recipe.lines:
        needed = base_quantity(line.quantity, line.unit)
        gap = needed - context.stock.get(line.ingredient_id, EMPTY_STOCK).total
        if gap > 0:
            missing.append({
                "ingredient_id": line.ingredient_id, "name": line.ingredient.name,
                "quantity": decimal_text(ceil_quantity(gap, line.unit)), "unit": line.unit,
            })
    if details:
        reasons.append(f"库存覆盖率 {decimal_text(details['stock'])}%")
    reasons.append(f"还需补买 {len(missing)} 种食材" if missing else "现有库存满足食材需求")
    return {
        "recipe_id": recipe.id, "name": recipe.name, "cooking_time": recipe.cooking_time,
        "servings": recipe.servings, "score": decimal_text(total), "reasons": reasons, "missing": missing,
        "score_details": {key: decimal_text(points) for key, points in (details or {}).items()},
    }


def rank_fallback(candidates, context, top_n):
    ranked = sorted(candidates, key=lambda recipe: (-len(expiring_hits(recipe, context)), recipe.id))
    return [recommendation_view(recipe, context) for recipe in ranked[:top_n]]


def recommend(user_id, options, today, recipe_ids=None):
    top_n, limit, weights = options
    preference = get_preference(user_id)
    limits = [value for value in (limit, preference["max_cooking_time"]) if value is not None]
    time_limit = min(limits) if limits else None
    avoid = set(preference["avoid_ingredients"])
    candidates = [
        row for row in load_requirements(recipe_ids, time_limit=time_limit)
        if row.lines and avoid.isdisjoint(line.ingredient_id for line in row.lines)
    ]
    if not candidates:
        return {"items": [], "degraded": False}
    context = RecommendContext(
        active_stock(user_id, today), set(preference["taste_preferences"]), time_limit,
        {key: Decimal(value) for key, value in preference["nutrition_targets"].items()},
    )
    try:
        ranked = []
        for recipe in candidates:
            details = {key: scorer(recipe, context) for key, scorer in SCORERS.items()}
            total = sum(details[key] * weights[key] for key in weights)
            ranked.append((recipe, total, details))
        ranked.sort(key=lambda row: (-row[1], -row[2]["expiring"], row[0].id))
    except Exception as error:
        current_app.logger.warning("recommendation scorer failed (%s)", type(error).__name__)
        return {"items": rank_fallback(candidates, context, top_n), "degraded": True}
    return {
        "items": [recommendation_view(recipe, context, total, details) for recipe, total, details in ranked[:top_n]],
        "degraded": False,
    }
