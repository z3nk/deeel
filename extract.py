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
from datetime import date
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image
from dotenv import load_dotenv

from models import Deal, Item

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
   "Halal" goes in diet_flags only if a halal mark or the word "Halal" is printed.
3a. meats: lowercase list from chicken, beef, pork, lamb, turkey, duck, fish
   (ham/bacon/chorizo = pork; tuna/salmon/prawn = fish), taken from the product
   name or printed ingredients. Return [] only if the label says vegetarian/vegan
   or the full ingredients are readable and contain no meat or fish.
   Otherwise return null.
3b. kcal and protein_g: per whole pack, from the printed nutrition panel. If only
   per-100g values are printed and the pack weight is printed, scale them;
   otherwise null. Never estimate.
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
