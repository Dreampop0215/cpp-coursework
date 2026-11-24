from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..domain import ApiError, text_value
from ..models import User, db
from .common import timestamp_text


def user_view(user):
    return {"id": user.id, "username": user.username, "created_at": timestamp_text(user.created_at)}


def register(username, password):
    username = text_value(username, "username", 50)
    password = text_value(password, "password", 128, strip=False, minimum=8)
    if db.session.scalar(select(User.id).where(User.username == username)) is not None:
        raise ApiError("用户名已存在", field="username")
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.flush()
    return user_view(user)


def login(username, password, session):
    username = text_value(username, "username", 50)
    password = text_value(password, "password", 128, strip=False, minimum=8)
    user = db.session.scalar(select(User).where(User.username == username))
    if user is None or not check_password_hash(user.password_hash, password):
        raise ApiError("登录信息无效", 401)
    session.clear()
    session["user_id"] = user.id
    return user_view(user)


def require_user(session):
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if type(user_id) is int and user_id > 0 else None
    if user is None:
        session.clear()
        raise ApiError("请登录", 401)
    return user_view(user)


def logout(session):
    session.clear()
