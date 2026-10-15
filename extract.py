"""
Claude vision pipeline: shelf-label or meal-deal-sign photo → validated Item or Deal.

Rules baked in:
- diet_flags and allergens come ONLY from printed label text; unreadable → empty list
- confidence is set by Claude based on label readability
- needs_review is forced True when confidence is medium or low
- One retry on a JSON parse failure
- Strip EXIF location data from every uploaded photo before storing
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image
from dotenv import load_dotenv

from models import Deal, Item
from openfoodfacts import normalise_barcode

load_dotenv()

_client: anthropic.Anthropic | None = None

MODEL = "claude-opus-4-6"


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

def strip_exif(image_path: Path) -> Path:
    """
    Remove EXIF metadata (including GPS location) from an image.
    Writes a clean copy in-place and returns the path.
    """
    img = Image.open(image_path)
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    clean.save(image_path)
    return image_path


def _encode_image(image_path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type) for an image file."""
    suffix = image_path.suffix.lower()
    media_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_map.get(suffix, "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ITEM_SYSTEM = """
You are a data-entry assistant for a supermarket shelf-label parser.
Your job is to read shelf-label photos and extract structured data as JSON.

CRITICAL RULES — read carefully:
1. diet_flags: list ONLY flags that are explicitly printed on the label
   (e.g. "Vegetarian", "Vegan", "Gluten Free"). If nothing is printed, return [].
2. allergens: list ONLY allergens explicitly named on the label
   (e.g. "Contains: milk, wheat"). If unreadable or absent, return [].
3. NEVER infer, guess, or assume diet or allergen status from the product name.
   "Halal" / "Kosher" go in diet_flags only if that certification mark or word
   is printed on the label.
3a. meats: lowercase list from chicken, beef, pork, lamb, turkey, duck, fish
   (ham/bacon/chorizo = pork; tuna/salmon/prawn = fish), taken from the product
   name or printed ingredients. Return [] only if the label says vegetarian/vegan
   or the full ingredients are readable and contain no meat or fish.
   Otherwise return null.
3a2. ingredients_text: copy the printed ingredients list exactly, including brackets and
   E-numbers. For single-ingredient whole foods sold without an ingredients list
   (e.g. a loose banana, bottled plain water), use the item itself, e.g. "Banana".
   Otherwise null.
3b. kcal and protein_g: per whole pack, from the printed nutrition panel. If only
   per-100g values are printed and the pack weight is printed, scale them;
   otherwise null. Never estimate.
3c. barcode: the digits under the product's barcode (on the pack or shelf label), only
   if every digit is clearly readable. Otherwise null. Never guess digits.
4. confidence: set to "high" if the label is fully readable, "medium" if partially
   readable, "low" if the label is too blurry, occluded, or absent.
5. needs_review: set to true if confidence is not "high", or if any field is ambiguous.
6. Return ONLY valid JSON — no markdown fences, no extra commentary.
"""

_ITEM_PROMPT = """
Extract data from this shelf label. Shop ID: {shop_id}. Photo date: {photo_date}.

Return a JSON object with exactly these fields:
{{
  "item_id": "<generate a short uuid>",
  "shop_id": "{shop_id}",
  "name": "<product name from label>",
  "category": "<main | snack | drink>",
  "price_gbp": <number>,
  "loyalty_price_gbp": <number or null>,
  "meal_deal_eligible": <true | false | null>,
  "temperature": "<hot | cold | ambient>",
  "diet_flags": ["<only if explicitly printed>"],
  "allergens": ["<only if explicitly printed>"],
  "ingredients_text": "<full ingredients if printed, else null>",
  "meats": ["<see rule 3a>"] or null,
  "kcal": <number per pack or null>,
  "protein_g": <number per pack or null>,
  "barcode": "<see rule 3c, or null>",
  "premium_range": <true | false | null>,
  "quality_rating": null,
  "source_image": "{filename}",
  "source_text": "<exact label wording for price, diet flags, and allergens>",
  "last_seen": "{photo_date}",
  "submitted_via": "{submitted_via}",
  "submitted_by": {submitted_by_json},
  "status": "pending",
  "confidence": "<high | medium | low>",
  "needs_review": <true | false>
}}
"""

_DEAL_SYSTEM = """
You are a data-entry assistant for a supermarket meal-deal sign parser.
Extract the deal pricing from the sign. Return ONLY valid JSON.
If prices are unreadable, set confidence to "low".
"""

_DEAL_PROMPT = """
Extract meal deal pricing from this sign. Shop ID: {shop_id}. Photo date: {photo_date}.

Return a JSON object with exactly these fields:
{{
  "deal_id": "<generate a short uuid>",
  "shop_id": "{shop_id}",
  "name": "<Meal Deal | Premium Meal Deal>",
  "price_gbp": <number>,
  "loyalty_price_gbp": <number or null>,
  "loyalty_scheme": "<Clubcard | Nectar | other | null>",
  "source_image": "{filename}",
  "last_seen": "{photo_date}",
  "submitted_by": {submitted_by_json},
  "status": "pending"
}}
"""


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response string."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find first { … }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text!r}")
    return json.loads(match.group())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_item(
    image_path: Path,
    shop_id: str,
    photo_date: date | None = None,
    submitted_via: str = "upload",
    submitted_by: str | None = None,
    strip_location: bool = True,
) -> Item:
    """
    Send a shelf-label photo to Claude and return a validated Item.
    Retries once on a JSON parse failure.
    Strips EXIF location data by default.
    """
    image_path = Path(image_path)
    if strip_location and image_path.exists():
        strip_exif(image_path)

    photo_date = photo_date or date.today()
    submitted_by_json = f'"{submitted_by}"' if submitted_by else "null"

    prompt = _ITEM_PROMPT.format(
        shop_id=shop_id,
        photo_date=photo_date.isoformat(),
        filename=image_path.name,
        submitted_via=submitted_via,
        submitted_by_json=submitted_by_json,
    )

    data, media_type = _encode_image(image_path)

    for attempt in range(2):
        try:
            response = _get_client().messages.create(
                model=MODEL,
                max_tokens=1024,
                system=_ITEM_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            raw = _extract_json(response.content[0].text)

            # Enforce needs_review for medium/low confidence
            if raw.get("confidence") in ("medium", "low"):
                raw["needs_review"] = True

            # Ensure item_id is present
            if not raw.get("item_id"):
                raw["item_id"] = str(uuid.uuid4())[:8]

            return Item(**raw)

        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == 1:
                raise RuntimeError(
                    f"extract_item failed after 2 attempts for {image_path.name}: {exc}"
                ) from exc


def extract_deal(
    image_path: Path,
    shop_id: str,
    photo_date: date | None = None,
    submitted_by: str | None = None,
    strip_location: bool = True,
) -> Deal:
    """
    Send a meal-deal sign photo to Claude and return a validated Deal.
    Retries once on a JSON parse failure.
    """
    image_path = Path(image_path)
    if strip_location and image_path.exists():
        strip_exif(image_path)

    photo_date = photo_date or date.today()
    submitted_by_json = f'"{submitted_by}"' if submitted_by else "null"

    prompt = _DEAL_PROMPT.format(
        shop_id=shop_id,
        photo_date=photo_date.isoformat(),
        filename=image_path.name,
        submitted_by_json=submitted_by_json,
    )

    data, media_type = _encode_image(image_path)

    for attempt in range(2):
        try:
            response = _get_client().messages.create(
                model=MODEL,
                max_tokens=512,
                system=_DEAL_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            raw = _extract_json(response.content[0].text)

            if not raw.get("deal_id"):
                raw["deal_id"] = str(uuid.uuid4())[:8]

            return Deal(**raw)

        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == 1:
                raise RuntimeError(
                    f"extract_deal failed after 2 attempts for {image_path.name}: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# Multi-product photos (upload screen)
# ---------------------------------------------------------------------------

_PHOTO_SYSTEM = _ITEM_SYSTEM + """
7. A photo may show MANY products (a whole shelf, several packs). Return one entry
   per distinct product you can identify. Never merge two products into one entry,
   and never invent a product you can't see.
8. Match each price to its product using the shelf-edge label directly below or
   beside it. If you can't tell which price belongs to a product, set price_gbp to
   null rather than guessing.
"""

_PHOTO_PROMPT = """
Shop ID: {shop_id}. The person filed this photo as: {photo_type_desc}.
{category_rule}

Return a JSON object with exactly these fields:
{{
  "kind": "<storefront | shelf | product | deal_sign | other>",
  "notes": "<one short sentence on anything unreadable or ambiguous, else empty>",
  "items": [
    {{
      "name": "<product name from the pack or label>",
      "category": "<main | snack | drink>",
      "price_gbp": <number or null if not readable / not matchable>,
      "loyalty_price_gbp": <number or null>,
      "meal_deal_eligible": <true | false | null>,
      "temperature": "<hot | cold | ambient>",
      "diet_flags": ["<only if explicitly printed>"],
      "allergens": ["<only if explicitly printed>"],
      "ingredients_text": "<see rule 3a2, or null>",
      "meats": ["<see rule 3a>"] or null,
      "kcal": <number per pack or null>,
      "protein_g": <number per pack or null>,
      "barcode": "<see rule 3c, or null>",
      "premium_range": <true | false | null>,
      "source_text": "<exact label wording used for price, diet flags and allergens>",
      "confidence": "<high | medium | low>"
    }}
  ],
  "deals": [
    {{
      "name": "<Meal Deal | Premium Meal Deal>",
      "price_gbp": <number>,
      "loyalty_price_gbp": <number or null>,
      "loyalty_scheme": "<Clubcard | Nectar | other | null>"
    }}
  ]
}}
Use [] for items or deals when there are none (e.g. a storefront photo).
"""

_TYPE_DESC = {
    "main": "a MAIN (sandwich, wrap, salad, pasta pot, soup, hot food)",
    "snack": "a SNACK (crisps, fruit, chocolate, yoghurt, nuts, sweets)",
    "drink": "a DRINK",
    "general": "a GENERAL shop photo (storefront, meal deal sign, or a mixed shelf)",
}


@dataclass
class PhotoExtraction:
    kind: str
    notes: str
    items: list[dict]      # product fields only; caller adds ids/shop/source and validates
    deals: list[dict]


def extract_photo(image_path: Path, shop_id: str, photo_type: str) -> PhotoExtraction:
    """
    Read every product (and any meal deal sign) in one photo.
    Returns raw dicts so the upload screen can show them for editing before they
    become Item/Deal records. Retries once on a JSON parse failure.
    """
    if photo_type in ("main", "snack", "drink"):
        category_rule = (
            f"Only extract {photo_type.upper()} products and set category to "
            f'"{photo_type}". Ignore other products in the background. '
            "Still report any meal deal sign in deals."
        )
    else:
        category_rule = "Extract every product of any category, and any meal deal sign."

    prompt = _PHOTO_PROMPT.format(
        shop_id=shop_id,
        photo_type_desc=_TYPE_DESC[photo_type],
        category_rule=category_rule,
    )
    data, media_type = _encode_image(Path(image_path))

    for attempt in range(2):
        try:
            response = _get_client().messages.create(
                model=MODEL,
                max_tokens=8192,
                system=_PHOTO_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            raw = _extract_json(response.content[0].text)
            items = [i for i in raw.get("items") or [] if isinstance(i, dict) and i.get("name")]
            if photo_type in ("main", "snack", "drink"):
                for i in items:
                    i["category"] = photo_type
            return PhotoExtraction(
                kind=raw.get("kind") or "other",
                notes=raw.get("notes") or "",
                items=items,
                deals=[d for d in raw.get("deals") or [] if isinstance(d, dict) and d.get("price_gbp")],
            )
        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == 1:
                raise RuntimeError(f"extract_photo failed after 2 attempts for {Path(image_path).name}: {exc}") from exc


def build_item(fields: dict, shop_id: str, source_rel: str, photo_date: date,
               submitted_by: str | None, submitted_via: str = "upload") -> Item:
    """Turn one (possibly user-edited) extracted product into a validated pending Item."""
    confidence = fields.get("confidence") if fields.get("confidence") in ("high", "medium", "low") else "medium"
    return Item(
        item_id=str(uuid.uuid4())[:8],
        shop_id=shop_id,
        name=fields["name"],
        category=fields["category"],
        price_gbp=float(fields["price_gbp"]),
        loyalty_price_gbp=fields.get("loyalty_price_gbp"),
        meal_deal_eligible=fields.get("meal_deal_eligible"),
        temperature=fields.get("temperature") or "ambient",
        diet_flags=[f.lower() for f in fields.get("diet_flags") or []],
        allergens=[a.lower() for a in fields.get("allergens") or []],
        ingredients_text=fields.get("ingredients_text"),
        meats=fields.get("meats"),
        kcal=fields.get("kcal"),
        protein_g=fields.get("protein_g"),
        barcode=normalise_barcode(fields.get("barcode")),
        external_fields=fields.get("external_fields") or {},
        premium_range=fields.get("premium_range"),
        source_image=source_rel,
        source_text=fields.get("source_text") or "",
        last_seen=photo_date,
        submitted_via=submitted_via,
        submitted_by=submitted_by,
        status="pending",
        confidence=confidence,
        needs_review=confidence != "high",
    )


def build_deal(fields: dict, shop_id: str, source_rel: str, photo_date: date,
               submitted_by: str | None) -> Deal:
    name = fields.get("name") if fields.get("name") in ("Meal Deal", "Premium Meal Deal") else "Meal Deal"
    scheme = fields.get("loyalty_scheme") if fields.get("loyalty_scheme") in ("Clubcard", "Nectar", "other") else None
    return Deal(
        deal_id=str(uuid.uuid4())[:8],
        shop_id=shop_id,
        name=name,
        price_gbp=float(fields["price_gbp"]),
        loyalty_price_gbp=fields.get("loyalty_price_gbp"),
        loyalty_scheme=scheme,
        source_image=source_rel,
        last_seen=photo_date,
        submitted_by=submitted_by,
        status="pending",
    )


def parse_preferences_from_text(free_text: str) -> dict:
    """
    Use Claude to convert a free-text preference string into structured
    preference fields (weights + filters). Returns a dict matching Preferences fields.
    """
    system = """
You parse a student's lunch preference string into structured JSON for a meal-deal finder.
Return ONLY valid JSON with these fields:
{
  "price_weight": <0-5, default 1>,
  "quality_weight": <0-5, default 1>,
  "warmth_weight": <0-5, default 1>,
  "max_price_gbp": <number or null>,
  "max_walking_minutes": <number, default 10>,
  "diet_flags": ["vegetarian" | "vegan" | ...],
  "allergens_exclude": ["nuts" | "gluten" | "dairy" | ...],
  "has_clubcard": <true | false>,
  "has_nectar": <true | false>
}
Examples:
- "cheap warm vegetarian" → price_weight=5, warmth_weight=4, diet_flags=["vegetarian"]
- "no nuts, I have a Clubcard" → allergens_exclude=["nuts"], has_clubcard=true
"""
    response = _get_client().messages.create(
        model=MODEL,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": free_text}],
    )
    return _extract_json(response.content[0].text)
