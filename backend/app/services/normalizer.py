import re
from dataclasses import dataclass

_UNIT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|gm|grams?|l|ltr|litres?|liters?|ml)\b", re.IGNORECASE)

_MASS_UNITS = {"kg", "g", "gm", "gram", "grams"}
_VOLUME_UNITS = {"l", "ltr", "litre", "litres", "liter", "liters", "ml"}


@dataclass(frozen=True)
class PackInfo:
    amount: float | None
    unit: str | None


@dataclass(frozen=True)
class UnitPrice:
    value: float | None
    label: str | None


def parse_pack_size(pack_size: str | None, name: str) -> PackInfo:
    match = _UNIT_PATTERN.search(f"{pack_size or ''} {name}")
    if not match:
        return PackInfo(None, None)
    raw_amount = match.group(1).replace(",", ".")
    try:
        amount = float(raw_amount)
    except ValueError:
        return PackInfo(None, None)
    return PackInfo(amount, match.group(2).lower())


def to_base(amount: float, unit: str) -> tuple[float, str] | None:
    if unit in _MASS_UNITS:
        grams = amount * 1000 if unit == "kg" else amount
        return grams, "per kg"
    if unit in _VOLUME_UNITS:
        millilitres = amount * 1000 if unit in ("l", "ltr", "litre", "litres", "liter", "liters") else amount
        return millilitres, "per litre"
    return None


def compute_unit_price(price: float | None, pack_size: str | None, name: str) -> UnitPrice:
    if price is None or price <= 0:
        return UnitPrice(None, None)
    info = parse_pack_size(pack_size, name)
    if info.amount is None or info.unit is None:
        return UnitPrice(None, None)
    base = to_base(info.amount, info.unit)
    if base is None or base[0] <= 0:
        return UnitPrice(None, None)
    base_quantity, label = base
    return UnitPrice(round((price / base_quantity) * 1000, 2), label)


def normalize_name(name: str) -> str:
    lowered = re.sub(r"\s*\(.*?\)\s*", " ", name.lower())
    stripped = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", stripped).strip()


_CATEGORY_HINTS: tuple[tuple[str, re.Pattern], ...] = (
    ("dairy", re.compile(r"milk|curd|yogurt|paneer|butter|cheese|ghee", re.I)),
    ("staples", re.compile(r"rice|atta|flour|dal|pulse|oil|sugar|salt", re.I)),
    ("beverages", re.compile(r"tea|coffee|juice|soda|water|drink", re.I)),
    ("snacks", re.compile(r"chip|biscuit|cookie|namkeen|chocolate|snack", re.I)),
    ("produce", re.compile(r"onion|potato|tomato|apple|banana|vegetable|fruit", re.I)),
    ("household", re.compile(r"detergent|soap|shampoo|clean|tissue|brush", re.I)),
)


def guess_category(name: str) -> str | None:
    for category, pattern in _CATEGORY_HINTS:
        if pattern.search(name):
            return category
    return None
