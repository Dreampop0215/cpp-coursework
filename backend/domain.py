import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction

from flask import current_app


CENT = Decimal("0.01")
QTY_MAX = Decimal("99999.00")
MONEY_MAX = Decimal("99999999.99")
DB_INT_MAX = 2_147_483_647
TIME_MAX = 1440
CSV_MAX_BYTES = 2 * 1024 * 1024
NUTRIENTS = ("calories", "protein", "fat", "carbohydrate")
UNITS = {
    "g": ("g", 1),
    "kg": ("g", 1000),
    "mL": ("mL", 1),
    "L": ("mL", 1000),
    "个": ("个", 1),
    "把": ("把", 1),
}
STOCK_STATES = ("fresh", "expiring", "expired")


class ApiError(Exception):
    def __init__(self, message, status=400, *, field=None, data=None):
        super().__init__(message)
        self.status = status
        self.data = {"field": field, "message": message} if field else data


def object_value(value, field="body"):
    if not isinstance(value, dict):
        raise ApiError("请提交一个对象", field=field)
    return value


def array_value(value, field, *, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        message = "请至少填写一项" if nonempty else "请提交数组"
        raise ApiError(message, field=field)
    return value


def text_value(value, field, limit=None, *, strip=True, minimum=1):
    if not isinstance(value, str):
        raise ApiError("请输入文本", field=field)
    value = value.strip() if strip else value
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ApiError("文本包含无效字符", field=field) from None
    if len(value) < minimum or (limit is not None and len(value) > limit):
        message = "请输入非空文本" if limit is None else f"请输入 {minimum}～{limit} 个字符"
        raise ApiError(message, field=field)
    if "\0" in value:
        raise ApiError("文本包含无效字符", field=field)
    return value


def int_value(value, field, minimum=0, maximum=DB_INT_MAX):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ApiError(f"请输入 {minimum}～{maximum} 的整数", field=field)
    return value


def id_value(value, field):
    return int_value(value, field, minimum=1)


def decimal_value(value, field, minimum=Decimal(0), maximum=QTY_MAX):
    try:
        amount = Decimal(str(value))
        if amount.is_finite() and minimum <= amount <= maximum:
            rounded = amount.quantize(CENT)
            if amount == rounded:
                return rounded.copy_abs() if not rounded else rounded
    except (InvalidOperation, ValueError):
        pass
    raise ApiError(f"请输入 {minimum}～{maximum} 的数值，最多两位小数", field=field)


def decimal_text(amount):
    if amount is None:
        return None
    return format(Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def choice(value, field, choices):
    if not isinstance(value, str) or value not in choices:
        raise ApiError(f"请选择 {'、'.join(choices)} 中的一项", field=field)
    return value


def date_value(value, field):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    except (TypeError, ValueError):
        pass
    raise ApiError("请输入 YYYY-MM-DD 格式的日期", field=field)


def date_range(values, start_key="start_date", end_key="end_date", defaults=(None, None)):
    start_raw, end_raw = values.get(start_key), values.get(end_key)
    start = date_value(start_raw, start_key) if start_raw else defaults[0]
    end = date_value(end_raw, end_key) if end_raw else defaults[1]
    if start and end and start > end:
        raise ApiError("开始日期不能晚于结束日期", field=end_key)
    return start, end


def text_list(values, field, *, nonempty=False, unique=False):
    items = array_value(values, field, nonempty=nonempty)
    cleaned = [text_value(value, f"{field}[{index}]") for index, value in enumerate(items)]
    return list(dict.fromkeys(cleaned)) if unique else cleaned


def base_quantity(amount, unit):
    return amount * UNITS[unit][1]


def same_dimension(unit, other):
    return UNITS[unit][0] == UNITS[other][0]


def ceil_quantity(amount, unit):
    hundredths = Fraction(amount) * 100 / UNITS[unit][1]
    ceiling = -(-hundredths.numerator // hundredths.denominator)
    return Decimal(ceiling).scaleb(-2)


def expiry_cutoff(today):
    remaining = (date.max - today).days
    return today + timedelta(days=min(remaining, current_app.config["EXPIRY_WARNING_DAYS"]))
