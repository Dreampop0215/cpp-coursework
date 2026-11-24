import logging
import os
import traceback
from datetime import datetime
from decimal import Decimal, DecimalException
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

import click
from dotenv import dotenv_values
from flask import Flask, g, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .domain import ApiError, CSV_MAX_BYTES
from .models import db


ROOT = Path(__file__).resolve().parent.parent
CONSTRAINT_MESSAGES = {
    "uq_users_username": ("username", "用户名已存在"),
    "uq_categories_type_name": ("name", "已有同名分类"),
    "uq_ingredients_category_name": ("name", "该分类中已有同名食材"),
    "uq_recipes_category_name": ("name", "该分类中已有同名菜谱"),
    "uq_shopping_ingredient": ("ingredient_id", "此食材已经在清单中"),
}


class DecimalJSONProvider(DefaultJSONProvider):
    def loads(self, value, **kwargs):
        kwargs.setdefault("parse_float", Decimal)
        try:
            return super().loads(value, **kwargs)
        except DecimalException as error:
            raise ValueError("JSON 数字超出支持范围") from error


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(ROOT / ".local"))
    app.json = DecimalJSONProvider(app)
    local_env = dotenv_values(ROOT / ".env")

    def setting(key, default=None):
        return os.environ.get(key, local_env.get(key, default))

    database_url = setting("DATABASE_URL")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "hide_parameters": True},
        SECRET_KEY=setting("SECRET_KEY"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=setting("SESSION_COOKIE_SECURE") == "1",
        FRONTEND_ORIGINS={
            value.strip().rstrip("/") for value in
            setting("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:5000").split(",")
            if value.strip()
        },
        APP_ZONE=ZoneInfo("Asia/Shanghai"),
        EXPIRY_WARNING_DAYS=int(setting("EXPIRY_WARNING_DAYS", "3")),
        MAX_CONTENT_LENGTH=CSV_MAX_BYTES + 64 * 1024,
        DEEPSEEK_API_KEY=setting("DEEPSEEK_API_KEY", ""),
        DEEPSEEK_MODEL=setting("DEEPSEEK_MODEL", "deepseek-flash"),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"] or not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("请在项目根目录的 .env 中设置 DATABASE_URL 和 SECRET_KEY")
    if app.config["EXPIRY_WARNING_DAYS"] < 0:
        raise RuntimeError("EXPIRY_WARNING_DAYS 须为非负整数")

    app.json.ensure_ascii = False
    db.init_app(app)
    with app.app_context():
        if db.engine.dialect.name == "sqlite":
            event.listen(db.engine, "connect", enable_sqlite_foreign_keys)
    CORS(app, resources={r"/api/.*": {"origins": sorted(app.config["FRONTEND_ORIGINS"])}}, supports_credentials=True)
    configure_logging(app)
    configure_requests(app)

    from .api import api
    from .seed import seed_demo

    app.register_blueprint(api, url_prefix="/api")

    @app.cli.command("init-db")
    def init_db_command():
        """Create the application tables in DATABASE_URL."""
        db.create_all()
        click.echo("数据库表已就绪")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Add example categories, ingredients and recipes."""
        counts = seed_demo()
        db.session.commit()
        click.echo(f"新增分类 {counts[0]} 个，食材 {counts[1]} 种，菜谱 {counts[2]} 道")

    return app


def enable_sqlite_foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")


def configure_logging(app):
    if app.testing:
        return
    directory = Path(app.instance_path) / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logfile = directory / "app.log"
    app.logger.setLevel(logging.INFO)
    if not any(getattr(handler, "baseFilename", None) == str(logfile) for handler in app.logger.handlers):
        handler = TimedRotatingFileHandler(logfile, when="midnight", backupCount=7, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        app.logger.addHandler(handler)


def configure_requests(app):
    @app.before_request
    def request_context():
        g.request_id = uuid4().hex
        g.started_at = perf_counter()
        g.today = datetime.now(app.config["APP_ZONE"]).date()

    @app.after_request
    def log_request(response):
        response.headers["X-Request-ID"] = g.request_id
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        app.logger.info(
            "%s %s %r %s %.1fms", g.request_id, request.method, request.path,
            response.status_code, (perf_counter() - g.started_at) * 1000,
        )
        return response

    @app.errorhandler(ApiError)
    def business_error(error):
        db.session.rollback()
        return jsonify(code=error.status, msg=str(error), data=error.data), error.status

    @app.errorhandler(IntegrityError)
    def constraint_error(error):
        original = error.orig
        constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
        if request.endpoint == "api.upload_csv":
            return business_error(ApiError("导入失败", data={"errors": [
                {"row": 1, "field": "file", "message": "目录数据已变化，请刷新后重新导入"},
            ]}))
        if constraint in CONSTRAINT_MESSAGES:
            field, message = CONSTRAINT_MESSAGES[constraint]
            return business_error(ApiError(message, field=field))
        if getattr(original, "pgcode", None) == "23503" or getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_FOREIGNKEY":
            return business_error(ApiError("记录已被引用或相关资料已变化，请刷新后重试"))
        return business_error(ApiError("写入数据违反约束，请检查填写内容"))

    @app.errorhandler(RequestEntityTooLarge)
    def large_request(error):
        if request.endpoint == "api.upload_csv":
            return business_error(ApiError("导入失败", data={"errors": [
                {"row": 1, "field": "file", "message": "CSV 不能超过 2 MiB"},
            ]}))
        return business_error(ApiError("请求内容过大", 413))

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400: "请求格式有误", 404: "记录不存在", 405: "请求方法不受支持"}
        return business_error(ApiError(messages.get(error.code, "请求失败"), error.code or 500))

    @app.errorhandler(Exception)
    def unexpected_error(error):
        location = " › ".join(f"{Path(frame.filename).name}:{frame.lineno}" for frame in traceback.extract_tb(error.__traceback__))
        app.logger.error("%s %s %s", g.get("request_id", "-"), type(error).__name__, location)
        message = "服务暂不可用，请稍后重试" if isinstance(error, OperationalError) else "系统繁忙，请稍后重试"
        return business_error(ApiError(message, 500))
