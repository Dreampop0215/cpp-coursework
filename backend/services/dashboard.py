from datetime import date

from flask import current_app
from sqlalchemy import case, func, select

from ..domain import STOCK_STATES, date_range, expiry_cutoff, id_value
from ..models import Category, Ingredient, Inventory, db
from .inventory import batch_view, expiring_batches
from .waste import aggregate_waste


def months_between(start, end):
    year, month = start.year, start.month
    while True:
        yield f"{year:04d}-{month:02d}"
        if (year, month) == (end.year, end.month):
            break
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def build_summary(user_id, filters, today):
    start, end = date_range(filters, defaults=(date(today.year, today.month, 1), today))
    category_id = id_value(filters["category_id"], "category_id") if filters.get("category_id") else None
    state = case(
        (Inventory.expiry_date < today, "expired"),
        (Inventory.expiry_date <= expiry_cutoff(today), "expiring"),
        else_="fresh",
    )
    stmt = (
        select(Category.id, Category.name, state, func.count(Inventory.id))
        .select_from(Inventory).join(Inventory.ingredient).join(Ingredient.category)
        .where(Inventory.user_id == user_id, Inventory.quantity > 0)
        .group_by(Category.id, Category.name, state).order_by(Category.name, Category.id)
    )
    if category_id is not None:
        stmt = stmt.where(Category.id == category_id)
    counts = dict.fromkeys(STOCK_STATES, 0)
    by_category = {}
    for key, label, status, count in db.session.execute(stmt):
        counts[status] += count
        by_category.setdefault(key, {"category_id": key, "name": label, "count": 0})["count"] += count
    preview = db.session.scalars(expiring_batches(user_id, today, category_id).limit(5))

    waste = aggregate_waste(user_id, {
        "group_by": "month", "start_date": start.isoformat(), "end_date": end.isoformat(), "category_id": category_id,
    })
    recorded = {item["key"]: item for item in waste["items"]}
    monthly = [
        recorded.get(month, {"key": month, "label": month, "count": 0, "amount": "0.00", "quantities": []})
        for month in months_between(start, end)
    ]
    return {
        "today": today.isoformat(), "start_date": start.isoformat(), "end_date": end.isoformat(),
        "expiry_warning_days": current_app.config["EXPIRY_WARNING_DAYS"],
        "inventory_counts": {**counts, "total": sum(counts.values())},
        "inventory_by_category": list(by_category.values()),
        "expiring_preview": [batch_view(batch, today) for batch in preview], "waste_monthly": monthly,
    }
