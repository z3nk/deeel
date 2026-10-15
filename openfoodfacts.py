"""
Fill missing nutrition and ingredients from Open Food Facts, by barcode only.

Open Food Facts is an open, crowd-sourced database (ODbL licence — credit it where
the data is shown). We use its official API, never scraping.

Rules:
- Lookup is by barcode (EAN-8/12/13/14), and only after the check digit validates,
  so a misread barcode can't pull in a different product. No name matching.
- Only fills fields that are missing: kcal, protein_g, ingredients_text. Never
  overwrites label values. NEVER touches allergens, diet flags or meats — those
  stay label-only (crowd-sourced data can be wrong or out of date).
- Values are per pack: per-100 g figures are scaled by the pack quantity, and left
  empty if Open Food Facts doesn't give one.
- This is the FALLBACK. nutrition_fill.py first checks our own label data for the
  same barcode, and only asks Open Food Facts for what's still missing.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

SOURCE = "Open Food Facts"
API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json?fields={fields}"
API_FIELDS = ("product_name,nutriments,ingredients_text_en,ingredients_text,"
              "quantity,product_quantity,product_quantity_unit")
USER_AGENT = "Deeelicious/1.0 (UCL hackathon; https://github.com/z3nk/deeelicious)"
TIMEOUT_S = 8

_cache: dict[str, dict | None] = {}


def normalise_barcode(raw) -> str | None:
    """Digits only; None unless it's a valid EAN/UPC (8, 12, 13 or 14 digits, good check digit)."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) not in (8, 12, 13, 14):
        return None
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return digits if (10 - total % 10) % 10 == check else None


def _fetch(barcode: str) -> dict | None:
    req = urllib.request.Request(
        API_URL.format(barcode=barcode, fields=API_FIELDS),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if data.get("status") != 1:
        return None
    return data.get("product") or None


_QUANTITY = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l|cl)\s*$", re.IGNORECASE)
_TO_BASE = {"g": 1, "ml": 1, "kg": 1000, "l": 1000, "cl": 10}


def pack_quantity(product: dict) -> float | None:
    """Grams / ml in one pack. Multipacks ('4 x 330 ml') and anything unclear → None."""
    try:
        value = float(product.get("product_quantity"))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    match = _QUANTITY.match(str(product.get("quantity") or ""))
    if match:
        return float(match.group(1).replace(",", ".")) * _TO_BASE[match.group(2).lower()]
    return None


def per_pack(product: dict) -> dict:
    """kcal / protein_g / ingredients_text for the whole pack, where derivable."""
    out: dict = {}
    nutriments = product.get("nutriments") or {}
    quantity = pack_quantity(product)
    if quantity and quantity > 0:
        for field, key in (("kcal", "energy-kcal_100g"), ("protein_g", "proteins_100g")):
            value = nutriments.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                out[field] = round(value * quantity / 100, 1)
    ingredients = (product.get("ingredients_text_en") or product.get("ingredients_text") or "").strip()
    if ingredients:
        out["ingredients_text"] = ingredients
    return out


def lookup(barcode) -> dict | None:
    """Per-pack values for a barcode, or None. Cached per process."""
    code = normalise_barcode(barcode)
    if code is None:
        return None
    if code not in _cache:
        product = _fetch(code)
        _cache[code] = per_pack(product) if product else None
    return _cache[code]
