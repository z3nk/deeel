"""
Fill missing nutrition and ingredients from Open Food Facts, by barcode only.

Open Food Facts is an open, crowd-sourced database (ODbL licence — credit it where
the data is shown). We use its official API, never scraping.

Rules:
- Lookup is by barcode (EAN-8/12/13/14) when one was read, and only after the check
  digit validates. Otherwise search_by_name() tries a strict name match (UK products,
  most of our name's words must match, pack sizes must agree for per-pack values);
  its source label names the matched product so bad matches can be spotted.
- Only fills fields that are missing: kcal, protein_g, ingredients_text, allergens.
  Never overwrites label values. Never touches diet flags or meats.
- Allergens from here are crowd-sourced: the optimiser lets them mark a product as
  UNSAFE but never as safe for an allergy filter (see optimiser.hard_filter).
- Values are per pack: per-100 g figures are scaled by the pack quantity, and left
  empty if Open Food Facts doesn't give one.
- This is the FALLBACK. nutrition_fill.py first checks our own label data for the
  same barcode, and only asks Open Food Facts for what's still missing.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE = "Open Food Facts"
API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json?fields={fields}"
API_FIELDS = ("product_name,nutriments,ingredients_text_en,ingredients_text,"
              "quantity,product_quantity,product_quantity_unit,allergens_tags")

# Open Food Facts allergen tags → the app's allergen names (lowercase, as the filters use).
# Peanuts also count as "nuts" so the Nuts filter errs on the safe side.
ALLERGEN_TAGS = {
    "en:gluten": ["gluten"], "en:milk": ["milk"], "en:eggs": ["egg"],
    "en:nuts": ["nuts"], "en:peanuts": ["peanuts", "nuts"], "en:sesame-seeds": ["sesame"],
    "en:soybeans": ["soy"], "en:fish": ["fish"], "en:crustaceans": ["shellfish"],
    "en:molluscs": ["shellfish"], "en:celery": ["celery"], "en:mustard": ["mustard"],
    "en:sulphur-dioxide-and-sulphites": ["sulphites"], "en:lupin": ["lupin"],
}
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
    # An empty tag list may just mean nobody entered them, so only fill when some are listed
    allergens = sorted({a for tag in product.get("allergens_tags") or [] for a in ALLERGEN_TAGS.get(tag, [])})
    if allergens:
        out["allergens"] = allergens
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


# ---------------------------------------------------------------------------
# Name search — for products whose barcode wasn't readable
# ---------------------------------------------------------------------------

SEARCH_URL = ("https://world.openfoodfacts.org/cgi/search.pl?search_terms={terms}&search_simple=1"
              "&action=process&json=1&page_size=10&fields=code,brands,{fields}"
              "&tagtype_0=countries&tag_contains_0=contains&tag_0=united-kingdom")
SEARCH_MIN_INTERVAL_S = 6.5      # Open Food Facts asks for ≤ 10 search requests a minute
MIN_NAME_OVERLAP = 0.75          # share of our name's words that must appear in the match
MIN_NAME_WORDS = 2               # one-word names ("Oasis") are too ambiguous to match

_STOPWORDS = {"and", "with", "the", "of", "in", "a", "on", "for", "by", "sandwich", "pack"}
_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|g|kg|l|cl)\b", re.IGNORECASE)
_last_search = 0.0
_search_cache: dict[str, list[dict]] = {}


def name_words(text: str) -> set[str]:
    text = _SIZE.sub(" ", (text or "").lower().replace("&", " and ").replace("'s", "s"))
    return {w for w in re.findall(r"[a-z0-9]+", text) if w not in _STOPWORDS and not w.isdigit()}


def name_size(text: str) -> float | None:
    """Pack size in g/ml written in a product name, e.g. 'Coke 500ml' → 500."""
    m = _SIZE.search(text or "")
    return float(m.group(1).replace(",", ".")) * _TO_BASE[m.group(2).lower()] if m else None


def best_name_match(our_name: str, candidates: list[dict]) -> dict | None:
    """The candidate whose brand + name covers most of our name's words, if good enough."""
    ours = name_words(our_name)
    if len(ours) < MIN_NAME_WORDS:
        return None
    our_size = name_size(our_name)

    def score(product: dict) -> tuple[float, int]:
        theirs = name_words(f"{product.get('brands') or ''} {product.get('product_name') or ''}")
        overlap = len(ours & theirs) / len(ours)
        same_size = int(our_size is not None and pack_quantity(product) == our_size)
        return overlap, same_size

    scored = [(score(p), p) for p in candidates if p.get("product_name")]
    good = [(s, p) for s, p in scored if s[0] >= MIN_NAME_OVERLAP]
    return max(good, key=lambda sp: sp[0])[1] if good else None


def _search(terms: str) -> list[dict]:
    global _last_search
    key = " ".join(sorted(name_words(terms)))
    if key in _search_cache:
        return _search_cache[key]
    wait = SEARCH_MIN_INTERVAL_S - (time.monotonic() - _last_search)
    if wait > 0:
        time.sleep(wait)
    _last_search = time.monotonic()
    req = urllib.request.Request(
        SEARCH_URL.format(terms=urllib.parse.quote(terms), fields=API_FIELDS),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S * 2) as resp:
            products = json.loads(resp.read().decode()).get("products") or []
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return []        # not cached, so a later run retries
    _search_cache[key] = products
    return products


def search_by_name(name: str) -> tuple[dict, str] | None:
    """
    (per-pack values, matched product label) for a strict name match, or None.
    Per-pack kcal/protein are dropped when our name states a pack size that differs
    from the product's, since a different size would give wrong totals.
    """
    if len(name_words(name)) < MIN_NAME_WORDS:
        return None
    match = best_name_match(name, _search(name))
    if match is None:
        return None
    values = per_pack(match)
    our_size = name_size(name)
    if our_size is not None and pack_quantity(match) != our_size:
        values.pop("kcal", None)
        values.pop("protein_g", None)
    label = " ".join(x for x in (match.get("brands", "").split(",")[0].strip(), match.get("product_name", "")) if x)
    return (values, label) if values else None
