from io import BytesIO
from urllib.parse import urlsplit

from flask import Blueprint, current_app, g, jsonify, request, send_file, session

from .domain import ApiError, object_value
from .models import Category, Ingredient, Inventory, Recipe, ShoppingList, db
from .services import auth, catalog, csv_io, dashboard, deepseek, inventory, preferences, recipes, recommendations, shopping, waste
from .services.common import find, page_args


api = Blueprint("api", __name__)


def body():
    return object_value(request.get_json(silent=True))


def result(data=None):
    return jsonify(code=0, msg="ok", data=data)


def saved(data=None):
    db.session.commit()
    return result(data)


def origin_of(referer):
    try:
        url = urlsplit(referer)
    except ValueError:
        return ""
    if url.scheme in ("http", "https") and url.netloc:
        return f"{url.scheme}://{url.netloc}"
    return ""


@api.before_request
def authorize():
    if request.method == "OPTIONS":
        return
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("Origin") or origin_of(request.headers.get("Referer", ""))
        if origin not in current_app.config["FRONTEND_ORIGINS"]:
            raise ApiError("请求来源不被允许", 403)
    if request.endpoint not in ("api.register", "api.login"):
        if request.endpoint == "api.generate_shopping_list" and db.engine.dialect.name == "postgresql":
            db.session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        g.user = auth.require_user(session)


@api.post("/auth/register")
def register():
    payload = body()
    return saved(auth.register(payload.get("username"), payload.get("password")))


@api.post("/auth/login")
def login():
    payload = body()
    return result(auth.login(payload.get("username"), payload.get("password"), session))


@api.post("/auth/logout")
def logout():
    return result(auth.logout(session))


@api.get("/auth/me")
def me():
    return result(g.user)


@api.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "GET":
        return result(catalog.get_categories(request.args, *page_args(request.args)))
    return saved(catalog.save_category(None, body()))


@api.route("/categories/<int:record_id>", methods=["GET", "PUT", "DELETE"])
def category_detail(record_id):
    if request.method == "GET":
        return result(catalog.category_view(find(Category, record_id)))
    if request.method == "PUT":
        return saved(catalog.save_category(record_id, body()))
    catalog.delete_catalog("categories", record_id)
    return saved()


@api.route("/ingredients", methods=["GET", "POST"])
def ingredients():
    if request.method == "GET":
        return result(catalog.get_ingredients(request.args, *page_args(request.args)))
    return saved(catalog.save_ingredient(None, body()))


@api.route("/ingredients/<int:record_id>", methods=["GET", "PUT", "DELETE"])
def ingredient_detail(record_id):
    if request.method == "GET":
        return result(catalog.ingredient_view(find(Ingredient, record_id)))
    if request.method == "PUT":
        return saved(catalog.save_ingredient(record_id, body()))
    catalog.delete_catalog("ingredients", record_id)
    return saved()


@api.route("/inventory", methods=["GET", "POST"])
def batches():
    if request.method == "GET":
        return result(inventory.get_batches(g.user["id"], request.args, *page_args(request.args), g.today))
    return saved(inventory.save_batch(g.user["id"], None, body(), g.today))


@api.get("/inventory/expiring")
def expiring():
    return result(inventory.get_batches(g.user["id"], request.args, *page_args(request.args), g.today, expiring=True))


@api.route("/inventory/<int:record_id>", methods=["GET", "PUT", "DELETE"])
def batch_detail(record_id):
    user_id = g.user["id"]
    if request.method == "GET":
        row = find(Inventory, record_id, user_id=user_id)
        return result(inventory.batch_view(row, g.today))
    if request.method == "PUT":
        return saved(inventory.save_batch(user_id, record_id, body(), g.today))
    inventory.delete_batch(user_id, record_id)
    return saved()


@api.route("/recipes", methods=["GET", "POST"])
def recipe_list():
    if request.method == "GET":
        return result(recipes.get_recipes(request.args, *page_args(request.args)))
    return saved(recipes.save_recipe(None, body()))


@api.route("/recipes/<int:record_id>", methods=["GET", "PUT", "DELETE"])
def recipe_detail(record_id):
    if request.method == "GET":
        return result(recipes.get_recipe(record_id))
    if request.method == "PUT":
        return saved(recipes.save_recipe(record_id, body()))
    db.session.delete(find(Recipe, record_id, lock=True))
    return saved()


@api.get("/recommendations")
def recommend():
    options = recommendations.options_from(request.args)
    return result(recommendations.recommend(g.user["id"], options, g.today))


@api.post("/recommendations/<int:recipe_id>/explain")
def explain(recipe_id):
    options = recommendations.options_from(body())
    rec = recommendations.recommend(g.user["id"], options, g.today, recipe_ids=[recipe_id])
    if not rec["items"]:
        raise ApiError("这道菜谱已不存在或不符合当前偏好", 404)
    db.session.rollback()
    return result(deepseek.explain_recommendation(rec["items"][0]))


@api.route("/shopping-lists", methods=["GET", "POST"])
def shopping_lists():
    if request.method == "GET":
        return result(shopping.get_lists(g.user["id"], request.args, *page_args(request.args)))
    return saved(shopping.save_list(g.user["id"], None, body()))


@api.post("/shopping-lists/generate")
def generate_shopping_list():
    return saved(shopping.generate_list(g.user["id"], body(), g.today))


@api.route("/shopping-lists/<int:record_id>", methods=["GET", "PUT", "DELETE"])
def shopping_list_detail(record_id):
    user_id = g.user["id"]
    if request.method == "GET":
        return result(shopping.get_list(user_id, record_id))
    if request.method == "PUT":
        return saved(shopping.save_list(user_id, record_id, body()))
    db.session.delete(find(ShoppingList, record_id, user_id=user_id, lock=True))
    return saved()


@api.post("/shopping-lists/<int:list_id>/items")
def shopping_items(list_id):
    return saved(shopping.update_item(g.user["id"], list_id, None, body()))


@api.route("/shopping-lists/<int:list_id>/items/<int:item_id>", methods=["PUT", "DELETE"])
def shopping_item_detail(list_id, item_id):
    if request.method == "PUT":
        return saved(shopping.update_item(g.user["id"], list_id, item_id, body()))
    return saved(shopping.delete_item(g.user["id"], list_id, item_id))


@api.route("/waste-logs", methods=["GET", "POST"])
def waste_logs():
    if request.method == "GET":
        return result(waste.list_waste(g.user["id"], request.args, *page_args(request.args)))
    return saved(waste.record_waste(g.user["id"], body(), g.today))


@api.get("/statistics/waste")
def waste_statistics():
    return result(waste.aggregate_waste(g.user["id"], request.args))


@api.route("/preferences", methods=["GET", "PUT"])
def user_preference():
    if request.method == "GET":
        return result(preferences.get_preference(g.user["id"]))
    return saved(preferences.save_preference(g.user["id"], body()))


@api.post("/import/<kind>")
def upload_csv(kind):
    if kind not in csv_io.HEADERS:
        raise ApiError("资料类型不存在", 404)
    file = request.files.get("file")
    if file is None:
        raise csv_io.failure([csv_io.row_error(1, "file", "请上传 CSV 文件")])
    return saved({"inserted_count": csv_io.import_csv(kind, file)})


@api.get("/export/<kind>")
def download_csv(kind):
    if kind not in csv_io.HEADERS:
        raise ApiError("资料类型不存在", 404)
    filename, contents = csv_io.export_csv(kind)
    return send_file(BytesIO(contents), mimetype="text/csv", as_attachment=True, download_name=filename)


@api.get("/dashboard/summary")
def dashboard_summary():
    return result(dashboard.build_summary(g.user["id"], request.args, g.today))
