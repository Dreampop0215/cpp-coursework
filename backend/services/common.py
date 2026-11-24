from datetime import timezone

from flask import current_app
from sqlalchemy import select

from ..domain import ApiError, choice, int_value
from ..models import db


def timestamp_text(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(current_app.config["APP_ZONE"]).isoformat()


def find(model, record_id, *, user_id=None, lock=False):
    stmt = select(model).where(model.id == record_id)
    if user_id is not None:
        stmt = stmt.where(model.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.session.scalar(stmt)
    if row is None:
        raise ApiError("记录不存在", 404)
    return row


def assign(row, fields):
    for key, value in fields.items():
        setattr(row, key, value)
    return row


def page_args(args):
    return (
        int_value(args.get("page", 1), "page", 1),
        int_value(args.get("page_size", 20), "page_size", 1, 100),
    )


def paginate(stmt, page, page_size, view):
    result = db.paginate(stmt, page=page, per_page=page_size, max_per_page=100, error_out=False)
    return {
        "items": [view(row) for row in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.per_page,
    }


def keyword_filter(stmt, column, filters, key="keyword"):
    keyword = filters.get(key, "").strip()
    return stmt.where(column.icontains(keyword, autoescape=True)) if keyword else stmt


def ordered(stmt, filters, column, tie_breaker, *, default="asc"):
    order = choice(filters.get("order", default), "order", ("asc", "desc"))
    stmt = stmt.order_by(None)
    if order == "desc":
        return stmt.order_by(column.desc(), tie_breaker.desc())
    return stmt.order_by(column, tie_breaker)
