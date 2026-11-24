import csv
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateSchema, DropSchema

import backend
from backend import create_app
from backend.models import db
from backend.services import deepseek, recommendations


ORIGIN = {"Origin": "http://localhost:5173"}
CREDENTIALS = {"username": "林", "password": " 密码 Abcd 1234 "}
OTHER = {"username": "周", "password": "test-password"}
TODAY = "2026-11-20"


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 20, 12, tzinfo=tz)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(backend, "datetime", FixedClock)
    test_url = os.environ.get("TEST_DATABASE_URL")
    config = {
        "TESTING": True, "SECRET_KEY": "test-secret", "DEEPSEEK_API_KEY": "",
        "SQLALCHEMY_DATABASE_URI": "sqlite://", "EXPIRY_WARNING_DAYS": 3,
    }
    admin = None
    if test_url:
        schema = f"sj_test_{uuid4().hex}"
        admin = create_engine(test_url, hide_parameters=True)
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        config.update(
            SQLALCHEMY_DATABASE_URI=test_url,
            SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"options": f"-c search_path={schema}"}},
        )
    app = create_app(config)
    try:
        with app.app_context():
            db.create_all()
        yield app
    finally:
        with app.app_context():
            db.engine.dispose()
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            admin.dispose()


def write(client, path, payload=None, method="post", status=200):
    options = {"headers": ORIGIN}
    if payload is not None:
        options["json"] = payload
    response = getattr(client, method)(f"/api{path}", **options)
    assert response.status_code == status, response.get_json()
    result = response.get_json()
    assert result["code"] == (0 if status == 200 else status)
    return result["data"]


def read(client, path, status=200):
    response = client.get(f"/api{path}")
    assert response.status_code == status, response.get_json()
    return response.get_json()["data"]


def login(client, credentials=CREDENTIALS):
    write(client, "/auth/register", credentials)
    write(client, "/auth/login", credentials)
    return client


def ingredient(client, category_id, name, unit):
    return write(client, "/ingredients", {
        "name": name, "category_id": category_id, "default_unit": unit, "shelf_life_days": 5,
    })


def setup_catalog(client):
    vegetables = write(client, "/categories", {"name": "食材", "type": "ingredient"})
    dishes = write(client, "/categories", {"name": "家常", "type": "recipe"})
    tomato = ingredient(client, vegetables["id"], "番茄", "g")
    egg = ingredient(client, vegetables["id"], "鸡蛋", "个")
    return dishes["id"], tomato["id"], egg["id"]


def recipe(client, category_id, name, quantities, *, minutes=15, servings=2, **extra):
    return write(client, "/recipes", {
        "name": name, "category_id": category_id, "cuisine": "家常", "difficulty": "简单",
        "servings": servings, "cooking_time": minutes, "steps": ["清洗食材", "烹制并装盘"],
        "taste_tags": ["清淡"], **extra,
        "ingredients": [
            {"ingredient_id": ingredient_id, "quantity": quantity, "unit": unit}
            for ingredient_id, quantity, unit in quantities
        ],
    })


def batch(client, ingredient_id, quantity, unit, expiry):
    return write(client, "/inventory", {
        "ingredient_id": ingredient_id, "quantity": quantity, "unit": unit,
        "purchase_date": "2026-11-10", "expiry_date": expiry,
    })


def discard(client, ingredient_id, batch_id, quantity, unit, *, status=200, waste_date=TODAY):
    return write(client, "/waste-logs", {
        "ingredient_id": ingredient_id, "inventory_id": batch_id, "quantity": quantity,
        "unit": unit, "amount": "2.50", "reason": "变质", "waste_date": waste_date,
    }, status=status)


def test_login_and_browser_origin(app):
    client = app.test_client()
    assert client.post("/api/auth/register", json=CREDENTIALS).status_code == 403
    assert client.post("/api/auth/register", json=CREDENTIALS, headers={"Origin": "http://untrusted.local"}).status_code == 403
    account = write(client, "/auth/register", {**CREDENTIALS, "username": "  林  "})
    assert set(account) == {"id", "username", "created_at"}
    write(client, "/auth/register", CREDENTIALS, status=400)
    write(client, "/auth/login", {**CREDENTIALS, "password": CREDENTIALS["password"].strip()}, status=401)
    response = client.post("/api/auth/login", json=CREDENTIALS, headers={"Referer": "http://localhost:5173/login"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    assert read(client, "/auth/me") == account
    write(client, "/auth/logout")
    read(client, "/auth/me", status=401)


def test_expiry_and_recommendation_example(app, monkeypatch):
    client = login(app.test_client())
    category_id, tomato, egg = setup_catalog(client)
    dish = recipe(client, category_id, "番茄鸡蛋", [(tomato, 200, "g"), (egg, 2, "个")])
    assert batch(client, tomato, 300, "g", "2026-11-19")["status"] == "expired"
    assert batch(client, tomato, "0.10", "kg", TODAY)["status"] == "expiring"
    assert batch(client, tomato, 0, "g", "2026-11-23")["status"] == "expiring"
    assert batch(client, tomato, 50, "g", "2026-11-24")["status"] == "fresh"
    batch(client, egg, 3, "个", "2026-11-30")
    assert read(client, "/inventory/expiring")["total"] == 1
    assert read(client, "/inventory?order=desc&page_size=1")["items"][0]["ingredient_name"] == "鸡蛋"
    write(client, "/preferences", {"taste_preferences": [" 清淡 ", "清淡"], "max_cooking_time": 30}, method="put")
    item = read(client, "/recommendations")["items"][0]
    assert item["score"] == "60.00"
    assert item["score_details"] == {
        "expiring": "25.00", "stock": "87.50", "taste": "100.00", "time": "50.00", "nutrition": "50.00",
    }
    assert item["missing"] == [{"ingredient_id": tomato, "name": "番茄", "quantity": "50.00", "unit": "g"}]
    assert read(client, "/recommendations?max_cooking_time=14")["items"] == []
    invalid_weights = {key: "0" for key in recommendations.DEFAULT_WEIGHTS}
    invalid_weights.update(stock="1", nutrition="1e-40")
    response = client.get("/api/recommendations", query_string={"weights": json.dumps(invalid_weights)})
    assert response.status_code == 400

    def broken_scorer(*_args):
        raise RuntimeError("test scorer")

    monkeypatch.setitem(recommendations.SCORERS, "stock", broken_scorer)
    degraded = read(client, "/recommendations")
    assert degraded["degraded"] and degraded["items"][0]["recipe_id"] == dish["id"]
    assert degraded["items"][0]["score"] is None and degraded["items"][0]["score_details"] == {}
    write(client, "/preferences", {"avoid_ingredients": [egg]}, method="put")
    assert read(client, "/recommendations")["items"] == []


def test_recommendation_ties_ignore_recipe_ingredient_order(app):
    client = login(app.test_client())
    category_id, tomato, egg = setup_catalog(client)
    ingredient_category_id = read(client, f"/ingredients/{tomato}")["category_id"]
    milk = ingredient(client, ingredient_category_id, "牛奶", "mL")["id"]
    quantities = [(tomato, 49, "g"), (egg, 73, "个"), (milk, 7, "mL")]
    for ingredient_id, amount, unit in [(tomato, 4, "g"), (egg, 29, "个"), (milk, 2, "mL")]:
        batch(client, ingredient_id, amount, unit, TODAY)

    first = recipe(client, category_id, "菜谱一", quantities)
    second = recipe(client, category_id, "菜谱二", reversed(quantities))

    items = read(client, "/recommendations")["items"]
    assert [item["recipe_id"] for item in items] == [first["id"], second["id"]]
    assert items[0]["score"] == items[1]["score"]


def test_shopping_needs_checkout_and_user_scope(app):
    client = login(app.test_client())
    outsider = login(app.test_client(), OTHER)
    category_id, tomato, _ = setup_catalog(client)
    recipes = [recipe(client, category_id, str(i), [(tomato, "1.00", "g")], servings=3) for i in range(3)]
    stock = batch(client, tomato, "0.99", "g", TODAY)
    read(outsider, f"/inventory/{stock['id']}", status=404)
    bought = write(client, "/shopping-lists/generate", {
        "name": "合并采购", "recipes": [{"recipe_id": dish["id"], "servings": 1} for dish in recipes],
    })
    item = bought["items"][0]
    assert item["quantity"] == "0.01" and item["unit"] == "g"
    path = f"/shopping-lists/{bought['id']}/items/{item['id']}"
    write(outsider, path, {"is_checked": True}, method="put", status=404)
    own = write(outsider, "/shopping-lists", {"name": "其他清单"})
    write(outsider, f"/shopping-lists/{own['id']}/items/{item['id']}", method="delete", status=404)
    assert write(client, path, {"is_checked": True}, method="put")["status"] == "completed"
    assert read(client, f"/inventory/{stock['id']}")["quantity"] == "0.99"
    assert write(client, path, method="delete")["status"] == "open"


def test_waste_atomicity_and_grouping(app):
    client = login(app.test_client())
    _, tomato, egg = setup_catalog(client)
    stock = batch(client, tomato, "0.50", "kg", "2026-11-19")
    discard(client, tomato, stock["id"], "1.00", "g", status=400)
    discard(client, tomato, stock["id"], "0.51", "kg", status=400)
    assert read(client, f"/inventory/{stock['id']}")["quantity"] == "0.50"
    discard(client, tomato, stock["id"], "100.00", "g")
    discard(client, tomato, stock["id"], "0.04", "kg")
    discard(client, egg, None, 2, "个")
    assert read(client, f"/inventory/{stock['id']}")["quantity"] == "0.36"
    assert read(client, "/statistics/waste?group_by=reason")["items"] == [{
        "key": "变质", "label": "变质", "count": 3, "amount": "7.50",
        "quantities": [{"unit": "g", "quantity": "140.00"}, {"unit": "个", "quantity": "2.00"}],
    }]
    write(client, f"/inventory/{stock['id']}", method="delete", status=400)
    summary = read(client, "/dashboard/summary?start_date=2026-09-15")
    assert [entry["amount"] for entry in summary["waste_monthly"]] == ["0.00", "0.00", "7.50"]


def test_stock_purchase_date_preserves_existing_waste_history(app):
    client = login(app.test_client())
    _, tomato, _ = setup_catalog(client)
    stock = batch(client, tomato, "100.00", "g", "2026-11-23")
    discard(client, tomato, stock["id"], "25.00", "g", waste_date="2026-11-18")
    path = f"/inventory/{stock['id']}"
    payload = {
        "ingredient_id": tomato, "quantity": "75.00", "unit": "g",
        "purchase_date": "2026-11-19", "expiry_date": "2026-11-23",
    }
    assert write(client, path, payload, method="put", status=400)["field"] == "purchase_date"
    assert read(client, path)["purchase_date"] == stock["purchase_date"]
    payload["purchase_date"] = "2026-11-18"
    assert write(client, path, payload, method="put")["purchase_date"] == "2026-11-18"


def test_json_decimal_precision_is_validated_before_rounding(app):
    client = login(app.test_client())
    _, tomato, _ = setup_catalog(client)
    payload = (
        f'{{"ingredient_id": {tomato}, "quantity": 2.50, "unit": "g", '
        f'"reason": "变质", "waste_date": "{TODAY}", "amount": AMOUNT}}'
    )
    excessive_precision = client.post(
        "/api/waste-logs", data=payload.replace("AMOUNT", "1.23000000000000001"),
        headers=ORIGIN, content_type="application/json",
    )
    assert excessive_precision.status_code == 400
    assert excessive_precision.get_json()["data"]["field"] == "amount"
    assert read(client, "/waste-logs")["total"] == 0
    exact = client.post(
        "/api/waste-logs", data=payload.replace("AMOUNT", "1.23"),
        headers=ORIGIN, content_type="application/json",
    )
    assert exact.status_code == 200
    assert exact.get_json()["data"]["amount"] == "1.23"


def test_postgres_concurrent_waste_deduction(app):
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("requires PostgreSQL row locking")
    client = login(app.test_client())
    _, tomato, _ = setup_catalog(client)
    stock = batch(client, tomato, 100, "g", TODAY)
    barrier = Barrier(2, timeout=5)

    def attempt():
        caller = app.test_client()
        write(caller, "/auth/login", CREDENTIALS)
        barrier.wait()
        response = caller.post("/api/waste-logs", json={
            "ingredient_id": tomato, "inventory_id": stock["id"], "quantity": 70, "unit": "g",
            "amount": "0.00", "reason": "损耗", "waste_date": TODAY,
        }, headers=ORIGIN)
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(attempt), executor.submit(attempt)
        assert sorted([first.result(), second.result()]) == [200, 400]
    assert read(client, f"/inventory/{stock['id']}")["quantity"] == "30.00"
    assert read(client, "/waste-logs")["total"] == 1


def test_csv_record_number_and_atomicity(app):
    client = login(app.test_client())
    setup_catalog(client)
    header = "name,category,default_unit,shelf_life_days\r\n"
    valid_row = '"香菜,小叶\n新鲜",食材,把,5\r\n'

    def upload(content):
        return client.post(
            "/api/import/ingredients", data={"file": (io.BytesIO(content.encode("utf-8-sig")), "items.csv")},
            headers=ORIGIN,
        )

    bad = upload(header + valid_row + "米,缺失分类,g,30\r\n")
    assert bad.status_code == 400
    assert bad.get_json()["data"]["errors"][0]["row"] == 3
    assert upload(header + '"米').get_json()["data"]["errors"][0]["row"] == 2
    assert read(client, "/ingredients")["total"] == 2
    assert upload(header + valid_row).get_json()["data"]["inserted_count"] == 1
    exported = client.get("/api/export/ingredients")
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.data.decode("utf-8-sig"), newline="")))
    assert rows[-1]["name"] == "香菜,小叶\n新鲜"


def test_recipe_detail_replacement_and_csv_roundtrip(app):
    client = login(app.test_client())
    category_id, tomato, egg = setup_catalog(client)
    dish = recipe(client, category_id, "家常菜", [(tomato, 100, "g"), (egg, 1, "个")], protein="12.50")
    path = f"/recipes/{dish['id']}"
    changed = {
        **dish, "steps": ["洗净，切块\n待用", "将剩余食材炒熟"],
        "ingredients": [{"ingredient_id": tomato, "quantity": "0.20", "unit": "kg"}],
    }
    updated = write(client, path, changed, method="put")
    assert updated["ingredients"][0]["quantity"] == "0.20"
    assert len(updated["ingredients"]) == 1
    csv_file = client.get("/api/export/recipes")
    write(client, path, method="delete")
    uploaded = client.post(
        "/api/import/recipes", data={"file": (io.BytesIO(csv_file.data), "recipes.csv")}, headers=ORIGIN,
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    recipes = read(client, "/recipes")
    restored = read(client, f"/recipes/{recipes['items'][0]['id']}")
    assert restored["steps"] == changed["steps"]
    assert restored["protein"] == "12.50" and restored["calories"] is None
    assert restored["ingredients"][0]["unit"] == "kg"


def test_deepseek_optional_explanation(app, monkeypatch):
    client = login(app.test_client())
    category_id, tomato, _ = setup_catalog(client)
    dish = recipe(client, category_id, "家常番茄", [(tomato, 200, "g")])
    endpoint = f"/recommendations/{dish['id']}/explain"
    app.config["DEEPSEEK_API_KEY"] = "test-key"
    baseline = read(client, "/recommendations")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "需要补买番茄 200 克。"}}]}

    def provider(url, *, headers, json, **kwargs):
        assert url == "https://api.deepseek.com/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert CREDENTIALS["username"] not in json["messages"][1]["content"]
        assert kwargs["allow_redirects"] is False
        return Response()

    monkeypatch.setattr(deepseek.requests, "post", provider)
    assert write(client, endpoint, {})["source"] == "deepseek"

    def unavailable(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(deepseek.requests, "post", unavailable)
    assert write(client, endpoint, {})["source"] == "rules"
    assert read(client, "/recommendations") == baseline
