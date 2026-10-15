"""
Seed data loader.

Two modes:
1. Photos present in seed/: run extract_item / extract_deal on each and batch-approve.
2. No photos: load FALLBACK_ITEMS — hardcoded realistic items for each shop so the
   optimiser and UI can be developed and tested before the seed walk happens.

Usage:
    python seed/load_seed.py            # auto-detects photos; falls back if none found
    python seed/load_seed.py --fallback # force fallback data regardless of photos
    python seed/load_seed.py --reset    # wipe items/deals tables first, then load
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from approval import approve, queue_deal, queue_item
from db import get_connection

SEED_DIR = Path(__file__).parent
TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Fallback seed data — realistic items for each shop
# Used when the seed walk hasn't happened yet.
# Update prices and allergens on the shelf walk.
# ---------------------------------------------------------------------------

FALLBACK_ITEMS = [
    # ── Tesco Express ──────────────────────────────────────────────────────
    {"item_id": "t-main-1", "shop_id": "tesco-tcr", "name": "Chicken Caesar Wrap",
     "category": "main", "price_gbp": 2.75, "loyalty_price_gbp": None,
     "meal_deal_eligible": True, "temperature": "cold",
     "diet_flags": [], "allergens": ["gluten", "milk", "egg"],
     "source_image": "fallback.jpg", "source_text": "£2.75 | gluten, milk, egg",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "t-main-2", "shop_id": "tesco-tcr", "name": "Ham & Cheese Sandwich",
     "category": "main", "price_gbp": 2.50, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": [], "allergens": ["gluten", "milk"],
     "source_image": "fallback.jpg", "source_text": "£2.50 | gluten, milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "t-main-3", "shop_id": "tesco-tcr", "name": "Falafel & Houmous Wrap",
     "category": "main", "price_gbp": 3.00, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegetarian", "vegan"],
     "allergens": ["gluten", "sesame"],
     "source_image": "fallback.jpg", "source_text": "£3.00 | vegan | gluten, sesame",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "t-snack-1", "shop_id": "tesco-tcr", "name": "Walkers Crisps",
     "category": "snack", "price_gbp": 1.00, "meal_deal_eligible": True,
     "temperature": "ambient", "diet_flags": ["vegetarian"], "allergens": ["milk"],
     "source_image": "fallback.jpg", "source_text": "£1.00 | vegetarian | milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "t-snack-2", "shop_id": "tesco-tcr", "name": "Fruit Pot",
     "category": "snack", "price_gbp": 1.25, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegetarian", "vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.25 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "t-drink-1", "shop_id": "tesco-tcr", "name": "Coca-Cola 500ml",
     "category": "drink", "price_gbp": 1.20, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.20 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "t-drink-2", "shop_id": "tesco-tcr", "name": "Still Water 500ml",
     "category": "drink", "price_gbp": 0.95, "meal_deal_eligible": True,
     "temperature": "ambient", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£0.95 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},

    # ── Sainsbury's ────────────────────────────────────────────────────────
    {"item_id": "s-main-1", "shop_id": "sainsburys-tcr", "name": "Falafel & Houmous Wrap",
     "category": "main", "price_gbp": 3.00, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegetarian", "vegan"],
     "allergens": ["gluten", "sesame"],
     "source_image": "fallback.jpg", "source_text": "£3.00 | vegan | gluten, sesame",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "s-main-2", "shop_id": "sainsburys-tcr", "name": "Chicken Caesar Wrap",
     "category": "main", "price_gbp": 3.20, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": [], "allergens": ["gluten", "milk", "egg"],
     "source_image": "fallback.jpg", "source_text": "£3.20 | gluten, milk, egg",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "s-snack-1", "shop_id": "sainsburys-tcr", "name": "Fruit Pot",
     "category": "snack", "price_gbp": 1.25, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.25 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "s-drink-1", "shop_id": "sainsburys-tcr", "name": "Innocent Juice",
     "category": "drink", "price_gbp": 1.60, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.60 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},

    # ── Pret A Manger ──────────────────────────────────────────────────────
    {"item_id": "p-main-1", "shop_id": "pret-tcr", "name": "Tomato & Basil Soup",
     "category": "main", "price_gbp": 3.95, "meal_deal_eligible": None,
     "temperature": "hot", "diet_flags": ["vegetarian"], "allergens": ["milk"],
     "source_image": "fallback.jpg", "source_text": "£3.95 | vegetarian | milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "p-main-2", "shop_id": "pret-tcr", "name": "Brie & Tomato Baguette",
     "category": "main", "price_gbp": 4.75, "meal_deal_eligible": None,
     "temperature": "cold", "diet_flags": ["vegetarian"], "allergens": ["gluten", "milk"],
     "source_image": "fallback.jpg", "source_text": "£4.75 | vegetarian | gluten, milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "p-snack-1", "shop_id": "pret-tcr", "name": "Banana",
     "category": "snack", "price_gbp": 0.60, "meal_deal_eligible": None,
     "temperature": "ambient", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£0.60 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "p-drink-1", "shop_id": "pret-tcr", "name": "Filter Coffee",
     "category": "drink", "price_gbp": 1.00, "meal_deal_eligible": None,
     "temperature": "hot", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.00 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},

    # ── Lidl ───────────────────────────────────────────────────────────────
    {"item_id": "l-main-1", "shop_id": "lidl-tcr", "name": "Chicken Salad Sandwich",
     "category": "main", "price_gbp": 1.89, "meal_deal_eligible": False,
     "temperature": "cold", "diet_flags": [], "allergens": ["gluten", "egg"],
     "source_image": "fallback.jpg", "source_text": "£1.89 | gluten, egg",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "l-snack-1", "shop_id": "lidl-tcr", "name": "Snack Pack Crackers",
     "category": "snack", "price_gbp": 0.79, "meal_deal_eligible": False,
     "temperature": "ambient", "diet_flags": ["vegetarian"], "allergens": ["gluten", "milk"],
     "source_image": "fallback.jpg", "source_text": "£0.79 | vegetarian | gluten, milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "l-drink-1", "shop_id": "lidl-tcr", "name": "Still Water 1L",
     "category": "drink", "price_gbp": 0.39, "meal_deal_eligible": False,
     "temperature": "ambient", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£0.39 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},

    # ── M&S Food ──────────────────────────────────────────────────────────
    {"item_id": "m-main-1", "shop_id": "ms-tcr", "name": "Chicken Tikka Wrap",
     "category": "main", "price_gbp": 4.00, "meal_deal_eligible": None,
     "temperature": "cold", "diet_flags": [], "allergens": ["gluten", "milk"],
     "source_image": "fallback.jpg", "source_text": "£4.00 | gluten, milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "m-main-2", "shop_id": "ms-tcr", "name": "Hoisin Duck Wrap",
     "category": "main", "price_gbp": 4.50, "meal_deal_eligible": None,
     "temperature": "cold", "diet_flags": [], "allergens": ["gluten", "sesame"],
     "source_image": "fallback.jpg", "source_text": "£4.50 | gluten, sesame",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "m-snack-1", "shop_id": "ms-tcr", "name": "Percy Pigs",
     "category": "snack", "price_gbp": 2.00, "meal_deal_eligible": None,
     "temperature": "ambient", "diet_flags": [], "allergens": ["gluten"],
     "source_image": "fallback.jpg", "source_text": "£2.00 | gluten",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "m-drink-1", "shop_id": "ms-tcr", "name": "Sparkling Water",
     "category": "drink", "price_gbp": 1.35, "meal_deal_eligible": None,
     "temperature": "ambient", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.35 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},

    # ── Waitrose ───────────────────────────────────────────────────────────
    {"item_id": "w-main-1", "shop_id": "waitrose-brunswick", "name": "Free Range Egg Mayo Sandwich",
     "category": "main", "price_gbp": 3.25, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": ["vegetarian"], "allergens": ["gluten", "egg", "milk"],
     "source_image": "fallback.jpg", "source_text": "£3.25 | vegetarian | gluten, egg, milk",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "w-main-2", "shop_id": "waitrose-brunswick", "name": "Smoked Salmon Wrap",
     "category": "main", "price_gbp": 4.50, "meal_deal_eligible": True,
     "temperature": "cold", "diet_flags": [], "allergens": ["gluten", "fish"],
     "source_image": "fallback.jpg", "source_text": "£4.50 | gluten, fish",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "w-snack-1", "shop_id": "waitrose-brunswick", "name": "Mixed Nuts",
     "category": "snack", "price_gbp": 1.75, "meal_deal_eligible": True,
     "temperature": "ambient", "diet_flags": ["vegan"], "allergens": ["nuts"],
     "source_image": "fallback.jpg", "source_text": "£1.75 | vegan | nuts",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
    {"item_id": "w-drink-1", "shop_id": "waitrose-brunswick", "name": "Sparkling Water 500ml",
     "category": "drink", "price_gbp": 1.20, "meal_deal_eligible": True,
     "temperature": "ambient", "diet_flags": ["vegan"], "allergens": [],
     "source_image": "fallback.jpg", "source_text": "£1.20 | vegan",
     "last_seen": TODAY, "submitted_via": "seed", "confidence": "high"},
]

# Meat + per-pack nutrition for fallback items: item_id → (meats, kcal, protein_g).
# Placeholder values — the seed walk replaces them with label readings.
FALLBACK_NUTRITION = {
    "t-main-1": (["chicken"], 480, 28),  "t-main-2": (["pork"], 410, 22),
    "t-main-3": ([], 450, 14),           "t-snack-1": ([], 130, 2),
    "t-snack-2": ([], 70, 1),            "t-drink-1": ([], 210, 0),
    "t-drink-2": ([], 0, 0),
    "s-main-1": ([], 440, 13),           "s-main-2": (["chicken"], 500, 30),
    "s-snack-1": ([], 70, 1),            "s-drink-1": ([], 160, 1),
    "p-main-1": ([], 220, 6),            "p-main-2": ([], 520, 21),
    "p-snack-1": ([], 105, 1),           "p-drink-1": ([], 5, 0),
    "l-main-1": (["chicken"], 360, 24),  "l-snack-1": ([], 150, 3),
    "l-drink-1": ([], 0, 0),
    "m-main-1": (["chicken"], 470, 32),  "m-main-2": (["duck"], 430, 20),
    "m-snack-1": (None, 160, 1),         "m-drink-1": ([], 0, 0),
    "w-main-1": ([], 390, 17),           "w-main-2": (["fish"], 420, 25),
    "w-snack-1": ([], 300, 9),           "w-drink-1": ([], 0, 0),
}

# Ingredients for fallback items (placeholder, typical of UK labels) — replaced on the seed walk
_BREAD = "Bread (Wheat Flour, Water, Yeast, Salt, Emulsifier (E471), Flour Treatment Agent (Ascorbic Acid))"
_WRAP = "Tortilla Wrap (Wheat Flour, Water, Rapeseed Oil, Raising Agents (E450, E500), Preservative (Calcium Propionate))"
FALLBACK_INGREDIENTS = {
    "t-main-1": f"{_WRAP}, Cooked Chicken (22%), Caesar Dressing (Rapeseed Oil, Water, Egg Yolk, Parmesan, Modified Maize Starch, Sugar, Flavouring), Lettuce",
    "t-main-2": f"{_BREAD}, Ham (Pork, Water, Salt, Dextrose, Stabiliser (E451), Preservative (Sodium Nitrite)), Cheddar Cheese, Butter",
    "t-main-3": f"{_WRAP}, Falafel (Chickpeas, Onion, Parsley, Cumin), Houmous (Chickpeas, Tahini, Lemon Juice, Garlic), Spinach, Red Pepper",
    "t-snack-1": "Potatoes, Sunflower Oil, Salt",
    "t-snack-2": "Pineapple, Melon, Grapes",
    "t-drink-1": "Carbonated Water, Sugar, Colour (Caramel E150d), Phosphoric Acid, Natural Flavourings Including Caffeine",
    "t-drink-2": "Natural Mineral Water",
    "s-main-1": f"{_WRAP}, Falafel (Chickpeas, Onion, Parsley, Cumin), Houmous (Chickpeas, Tahini, Lemon Juice), Spinach",
    "s-main-2": f"{_WRAP}, Cooked Chicken (24%), Caesar Dressing (Rapeseed Oil, Water, Egg Yolk, Parmesan, Glucose Syrup, Flavouring, Stabiliser (Xanthan Gum)), Lettuce",
    "s-snack-1": "Pineapple, Melon, Grapes",
    "s-drink-1": "Pressed Apple Juice, Pressed Orange Juice, Mango Puree",
    "p-main-1": "Tomatoes, Water, Onion, Cream (Milk), Basil, Rapeseed Oil, Garlic, Salt, Black Pepper",
    "p-main-2": "Baguette (Wheat Flour, Water, Salt, Yeast), Brie (Milk), Tomatoes, Basil, Butter",
    "p-snack-1": "Banana",
    "p-drink-1": "Coffee, Water",
    "l-main-1": f"{_BREAD}, Chicken (20%), Mayonnaise (Rapeseed Oil, Water, Egg, Modified Maize Starch, Preservative (Potassium Sorbate), Sweetener (Sucralose), Colour (Beta-Carotene)), Lettuce, Tomato",
    "l-snack-1": "Wheat Flour, Palm Oil, Cheese Powder (Milk), Glucose Syrup, Salt, Raising Agent (E503), Flavour Enhancer (Monosodium Glutamate), Flavouring",
    "l-drink-1": "Natural Mineral Water",
    "m-main-1": "Tortilla Wrap (Wheat Flour, Water, Rapeseed Oil, Salt), Chicken Tikka (Chicken (28%), Yoghurt (Milk), Spices, Garlic, Ginger), Mango Chutney (Mango, Sugar, Vinegar), Spinach",
    "m-main-2": "Tortilla Wrap (Wheat Flour, Water, Rapeseed Oil, Salt), Duck (25%), Hoisin Sauce (Sugar, Soybeans, Water, Vinegar, Sesame, Garlic, Modified Maize Starch), Cucumber, Spring Onion",
    "m-snack-1": "Glucose Syrup, Sugar, Gelatine (Pork), Fruit Juice from Concentrate, Acid (Citric Acid), Flavourings, Colours (Black Carrot, Paprika Extract), Glazing Agent (Carnauba Wax)",
    "m-drink-1": "Carbonated Natural Mineral Water",
    "w-main-1": "Bread (Wheat Flour, Water, Yeast, Salt), Free Range Egg (45%), Mayonnaise (Rapeseed Oil, Egg Yolk, Vinegar, Mustard), Cress",
    "w-main-2": "Tortilla Wrap (Wheat Flour, Water, Rapeseed Oil, Salt), Smoked Salmon (Fish) (28%), Soft Cheese (Milk), Spinach, Lemon Juice",
    "w-snack-1": "Cashew Nuts, Almonds, Hazelnuts, Brazil Nuts",
    "w-drink-1": "Carbonated Natural Mineral Water",
}

# Placeholder halal label so the Halal chip has something to show before the walk
FALLBACK_EXTRA_FLAGS = {"m-main-1": ["halal"]}

FALLBACK_DEALS = [
    {"deal_id": "deal-tesco", "shop_id": "tesco-tcr", "name": "Meal Deal",
     "price_gbp": 4.25, "loyalty_price_gbp": 3.85, "loyalty_scheme": "Clubcard",
     "source_image": "fallback.jpg", "last_seen": TODAY},
    {"deal_id": "deal-sainsburys", "shop_id": "sainsburys-tcr", "name": "Meal Deal",
     "price_gbp": 3.95, "loyalty_price_gbp": None, "loyalty_scheme": None,
     "source_image": "fallback.jpg", "last_seen": TODAY},
    {"deal_id": "deal-waitrose", "shop_id": "waitrose-brunswick", "name": "Meal Deal",
     "price_gbp": 5.50, "loyalty_price_gbp": None, "loyalty_scheme": None,
     "source_image": "fallback.jpg", "last_seen": TODAY},
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_fallback(conn, reset: bool = False) -> None:
    if reset:
        conn.execute("DELETE FROM items")
        conn.execute("DELETE FROM deals")
        conn.commit()
        print("Tables cleared.")

    loaded_items = 0
    for item in FALLBACK_ITEMS:
        meats, kcal, protein_g = FALLBACK_NUTRITION.get(item["item_id"], (None, None, None))
        item_id = queue_item(conn, {
            **item,
            "diet_flags": item["diet_flags"] + FALLBACK_EXTRA_FLAGS.get(item["item_id"], []),
            "meats": meats,
            "kcal": kcal,
            "protein_g": protein_g,
            "loyalty_price_gbp": item.get("loyalty_price_gbp"),
            "ingredients_text": FALLBACK_INGREDIENTS.get(item["item_id"]),
            "premium_range": None,
            "quality_rating": None,
            "needs_review": False,
            "submitted_by": None,
        })
        approve(conn, item_id, "item")
        loaded_items += 1

    loaded_deals = 0
    for deal in FALLBACK_DEALS:
        deal_id = queue_deal(conn, {**deal, "submitted_by": None})
        approve(conn, deal_id, "deal")
        loaded_deals += 1

    print(f"Loaded {loaded_items} items and {loaded_deals} deals from fallback data.")


def load_from_photos(conn, reset: bool = False) -> None:
    from extract import extract_deal, extract_item

    if reset:
        conn.execute("DELETE FROM items")
        conn.execute("DELETE FROM deals")
        conn.commit()
        print("Tables cleared.")

    photos = list(SEED_DIR.glob("*.jpg")) + list(SEED_DIR.glob("*.png")) + list(SEED_DIR.glob("*.webp"))
    if not photos:
        print("No photos found in seed/ — using fallback data.")
        load_fallback(conn)
        return

    ok, failed = 0, 0
    for photo in photos:
        shop_id = _infer_shop_id(photo.name)
        if shop_id is None:
            print(f"  SKIP {photo.name} — cannot infer shop_id (name must start with shop prefix)")
            continue
        try:
            if "deal" in photo.name.lower() or "sign" in photo.name.lower():
                record = extract_deal(photo, shop_id)
                deal_id = queue_deal(conn, record.model_dump())
                approve(conn, deal_id, "deal")
            else:
                record = extract_item(photo, shop_id, submitted_via="seed")
                item_id = queue_item(conn, record.model_dump())
                approve(conn, item_id, "item")
            print(f"  OK  {photo.name}")
            ok += 1
        except Exception as exc:
            print(f"  ERR {photo.name}: {exc}")
            failed += 1

    print(f"\nDone: {ok} loaded, {failed} failed.")


def _infer_shop_id(filename: str) -> str | None:
    """
    Infer shop_id from filename prefix, e.g.:
        tesco_wrap.jpg      → tesco-tcr
        sainsburys_deal.jpg → sainsburys-tcr
    """
    mapping = {
        "tesco": "tesco-tcr",
        "sainsburys": "sainsburys-tcr",
        "waitrose": "waitrose-brunswick",
        "ms": "ms-tcr",
        "marks": "ms-tcr",
        "lidl": "lidl-tcr",
        "pret": "pret-tcr",
    }
    lower = filename.lower()
    for prefix, shop_id in mapping.items():
        if lower.startswith(prefix):
            return shop_id
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load seed data into the database.")
    parser.add_argument("--fallback", action="store_true", help="Force fallback data (no photos)")
    parser.add_argument("--reset", action="store_true", help="Wipe items/deals tables before loading")
    args = parser.parse_args()

    conn = get_connection()

    if args.fallback:
        load_fallback(conn, reset=args.reset)
    else:
        load_from_photos(conn, reset=args.reset)

    # Quick verification
    item_count = conn.execute("SELECT COUNT(*) FROM items WHERE status='approved'").fetchone()[0]
    deal_count = conn.execute("SELECT COUNT(*) FROM deals WHERE status='approved'").fetchone()[0]
    print(f"\nDatabase: {item_count} approved items, {deal_count} approved deals.")
