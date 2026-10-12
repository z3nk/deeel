"""
Optimiser: hard filters, scoring, per-shop exact search, and shop ranking.

The score formula (from PLAN.md):
    U = w_p * (1 - P / P_max) + w_q * Q + w_h * H

where:
    P     = lunch price (deal price if bundled, else sum of 3 item prices)
    P_max = user's cap or £10 ceiling
    Q     = mean quality score across 3 items
    H     = 1 if main is hot, else 0
    w_*   = user weights (price/quality/warmth 0–5), normalised to sum to 1

Because U is additive across items, the best lunch per shop is found exactly
by independently choosing the best main, snack, and drink — no combination search needed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Optional

from models import Deal, Item, Lunch, Preferences, Shop

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_DAYS = 14          # items older than this are filtered out
P_MAX_DEFAULT = 10.0     # £ ceiling when user sets no cap
Q_UNRATED = 0.5          # quality score for items with no student rating
Q_PREMIUM_BONUS = 0.1    # bonus for premium-range items
WALK_SPEED_MPM = 80.0    # metres per minute (used to convert mins → metres in map)


# ---------------------------------------------------------------------------
# Row → model helpers
# ---------------------------------------------------------------------------

def _row_to_item(row: sqlite3.Row) -> Item:
    d = dict(row)
    d["diet_flags"] = json.loads(d["diet_flags"])
    d["allergens"] = json.loads(d["allergens"])
    d["meal_deal_eligible"] = (
        None if d["meal_deal_eligible"] is None else bool(d["meal_deal_eligible"])
    )
    d["premium_range"] = (
        None if d["premium_range"] is None else bool(d["premium_range"])
    )
    d["needs_review"] = bool(d["needs_review"])
    return Item(**d)


def _row_to_shop(row: sqlite3.Row) -> Shop:
    d = dict(row)
    from datetime import date as _date
    d["last_verified"] = _date.fromisoformat(d["last_verified"])
    return Shop(**d)


def _row_to_deal(row: sqlite3.Row) -> Deal:
    from datetime import date as _date
    d = dict(row)
    d["last_seen"] = _date.fromisoformat(d["last_seen"])
    return Deal(**d)


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

def hard_filter(items: list[Item], prefs: Preferences, today: date | None = None) -> list[Item]:
    """
    Return only items that pass all hard filters.

    Filters (all must pass):
    1. Status approved (or pending when user has no allergen needs)
    2. Carries every required diet flag
    3. Contains none of the excluded allergens; null allergens = excluded if any allergen filter set
    4. last_seen within STALE_DAYS
    5. (price cap applied at the lunch level, not item level)
    """
    today = today or date.today()
    cutoff = today - timedelta(days=STALE_DAYS)
    results = []

    for item in items:
        # 1. Status
        if prefs.allergens_exclude or prefs.diet_flags:
            if item.status != "approved":
                continue
        else:
            if item.status == "rejected":
                continue

        # 2. Diet flags — only applied to mains; snacks/drinks are assumed fine
        # (crisps, water, juice etc. often aren't explicitly labelled vegetarian/vegan)
        if prefs.diet_flags and item.category == "main":
            item_flags_lower = [f.lower() for f in item.diet_flags]
            if not all(req.lower() in item_flags_lower for req in prefs.diet_flags):
                continue

        # 3. Allergens — null allergens = unsafe when user has allergen needs
        if prefs.allergens_exclude:
            if not item.allergens:  # allergens unknown → exclude
                continue
            item_allergens_lower = [a.lower() for a in item.allergens]
            if any(excl.lower() in item_allergens_lower for excl in prefs.allergens_exclude):
                continue

        # 3b. Temperature preference (only applies to mains)
        if item.category == "main" and prefs.temperature_pref != "any":
            if prefs.temperature_pref == "hot" and item.temperature != "hot":
                continue
            if prefs.temperature_pref == "cold" and item.temperature == "hot":
                continue

        # 4. Freshness
        item_date = (
            date.fromisoformat(item.last_seen)
            if isinstance(item.last_seen, str)
            else item.last_seen
        )
        if item_date < cutoff:
            continue

        results.append(item)

    return results


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _weights_from_sort(prefs: Preferences) -> tuple[float, float, float]:
    """
    Map the sort dropdown to (w_price, w_quality, w_warmth) normalised to sum to 1.
    quality  → quality dominant
    price    → price dominant
    distance → equal weights (distance tie-break is applied at rank_shops level)
    """
    mapping = {
        "quality":  (1.0, 5.0, 1.0),
        "price":    (5.0, 1.0, 1.0),
        "distance": (1.0, 1.0, 1.0),
    }
    w_p, w_q, w_h = mapping[prefs.sort]
    total = w_p + w_q + w_h
    return w_p / total, w_q / total, w_h / total


# Keep legacy name for tests written before the sort field existed
def _normalise_weights(prefs: Preferences) -> tuple[float, float, float]:
    return _weights_from_sort(prefs)


def _quality_score(item: Item) -> float:
    q = Q_UNRATED if item.quality_rating is None else (item.quality_rating - 1) / 4
    if item.premium_range:
        q = min(1.0, q + Q_PREMIUM_BONUS)
    return q


def _effective_price(item: Item, prefs: Preferences) -> float:
    if prefs.has_clubcard and item.loyalty_price_gbp is not None:
        return item.loyalty_price_gbp
    if prefs.has_nectar and item.loyalty_price_gbp is not None:
        return item.loyalty_price_gbp
    return item.price_gbp


def score_lunch(
    main: Item,
    snack: Item,
    drink: Item,
    price_gbp: float,
    prefs: Preferences,
) -> float:
    """Compute U for a (main, snack, drink) triple at a given price."""
    w_p, w_q, w_h = _normalise_weights(prefs)
    p_max = prefs.max_price_gbp or P_MAX_DEFAULT

    price_term = max(0.0, 1 - price_gbp / p_max)
    quality_term = (_quality_score(main) + _quality_score(snack) + _quality_score(drink)) / 3
    warmth_term = 1.0 if main.temperature == "hot" else 0.0

    return w_p * price_term + w_q * quality_term + w_h * warmth_term


# ---------------------------------------------------------------------------
# Per-shop exact search
# ---------------------------------------------------------------------------

def best_lunch_for_shop(
    shop: Shop,
    items: list[Item],
    deals: list[Deal],
    prefs: Preferences,
) -> Optional[Lunch]:
    """
    Find the best Lunch for a single shop by trying separate and deal pricing.
    Returns None if no complete main+snack+drink combination exists.
    """
    mains  = [i for i in items if i.category == "main"  and i.shop_id == shop.shop_id]
    snacks = [i for i in items if i.category == "snack" and i.shop_id == shop.shop_id]
    drinks = [i for i in items if i.category == "drink" and i.shop_id == shop.shop_id]

    if not mains or not snacks or not drinks:
        return None

    p_max = prefs.max_price_gbp or P_MAX_DEFAULT
    best: Optional[Lunch] = None

    # ---- Separate mode ----
    # Pick best main, snack, drink independently by their per-item score contribution
    def _item_score(item: Item, prefs: Preferences) -> float:
        """Score an individual item's quality + warmth contribution (price handled at lunch level)."""
        w_p, w_q, w_h = _normalise_weights(prefs)
        q = _quality_score(item)
        h = 1.0 if item.temperature == "hot" and item.category == "main" else 0.0
        return w_q * q + w_h * h

    best_main  = max(mains,  key=lambda i: _item_score(i, prefs))
    best_snack = max(snacks, key=lambda i: _item_score(i, prefs))
    best_drink = max(drinks, key=lambda i: _item_score(i, prefs))

    sep_price = (
        _effective_price(best_main, prefs)
        + _effective_price(best_snack, prefs)
        + _effective_price(best_drink, prefs)
    )

    if sep_price <= p_max:
        sep_score = score_lunch(best_main, best_snack, best_drink, sep_price, prefs)
        best = Lunch(
            shop=shop,
            main=best_main,
            snack=best_snack,
            drink=best_drink,
            price_gbp=sep_price,
            used_deal=False,
            score=sep_score,
        )

    # ---- Deal mode ----
    shop_deals = [d for d in deals if d.shop_id == shop.shop_id]
    if shop_deals:
        deal = shop_deals[0]  # use the first (best) deal; could rank if multiple
        deal_price = (
            deal.loyalty_price_gbp
            if (prefs.has_clubcard or prefs.has_nectar) and deal.loyalty_price_gbp
            else deal.price_gbp
        )

        deal_mains  = [i for i in mains  if i.meal_deal_eligible]
        deal_snacks = [i for i in snacks if i.meal_deal_eligible]
        deal_drinks = [i for i in drinks if i.meal_deal_eligible]

        if deal_mains and deal_snacks and deal_drinks and deal_price <= p_max:
            dm = max(deal_mains,  key=lambda i: _item_score(i, prefs))
            ds = max(deal_snacks, key=lambda i: _item_score(i, prefs))
            dd = max(deal_drinks, key=lambda i: _item_score(i, prefs))

            deal_score = score_lunch(dm, ds, dd, deal_price, prefs)

            if best is None or deal_score > best.score:
                best = Lunch(
                    shop=shop,
                    main=dm,
                    snack=ds,
                    drink=dd,
                    price_gbp=deal_price,
                    used_deal=True,
                    deal=deal,
                    score=deal_score,
                )

    return best


# ---------------------------------------------------------------------------
# Shop ranking
# ---------------------------------------------------------------------------

def rank_shops(
    shops: list[Shop],
    items: list[Item],
    deals: list[Deal],
    prefs: Preferences,
    today: date | None = None,
) -> list[Lunch]:
    """
    Apply hard filters, find the best lunch per shop, rank by score (desc),
    break ties by walking_minutes (asc).
    Returns a list of Lunch objects (best first).
    """
    today = today or date.today()

    # Filter shops by walking limit
    in_range = [s for s in shops if s.walking_minutes <= prefs.max_walking_minutes]

    # Filter items
    filtered_items = hard_filter(items, prefs, today)

    results: list[Lunch] = []
    for shop in in_range:
        lunch = best_lunch_for_shop(shop, filtered_items, deals, prefs)
        if lunch is not None:
            results.append(lunch)

    results.sort(key=lambda l: (-l.score, l.shop.walking_minutes))
    return results


# ---------------------------------------------------------------------------
# "Why" line generation (uses Claude, called after ranking)
# ---------------------------------------------------------------------------

def top_lunches_for_shop(
    shop: Shop,
    items: list[Item],
    deals: list[Deal],
    prefs: Preferences,
    n: int = 3,
) -> list[Lunch]:
    """
    Return up to n Lunch objects for a single shop, each with a different main.
    Used to populate Section B (alternatives at the same shop).
    Snack and drink are kept as the best available; only the main varies.
    """
    mains  = [i for i in items if i.category == "main"  and i.shop_id == shop.shop_id]
    snacks = [i for i in items if i.category == "snack" and i.shop_id == shop.shop_id]
    drinks = [i for i in items if i.category == "drink" and i.shop_id == shop.shop_id]

    if not mains or not snacks or not drinks:
        return []

    p_max = prefs.max_price_gbp or P_MAX_DEFAULT
    shop_deals = [d for d in deals if d.shop_id == shop.shop_id]

    def _item_score(item: Item) -> float:
        w_p, w_q, w_h = _weights_from_sort(prefs)
        return w_q * _quality_score(item) + (w_h if item.temperature == "hot" and item.category == "main" else 0)

    # Best snack and drink stay fixed
    best_snack = max(snacks, key=_item_score)
    best_drink = max(drinks, key=_item_score)

    # Rank all mains and produce one Lunch per main
    ranked_mains = sorted(mains, key=_item_score, reverse=True)
    results: list[Lunch] = []

    for main in ranked_mains[:n]:
        sep_price = (
            _effective_price(main, prefs)
            + _effective_price(best_snack, prefs)
            + _effective_price(best_drink, prefs)
        )
        if sep_price > p_max:
            continue

        used_deal = False
        price = sep_price
        deal_obj = None

        if shop_deals and main.meal_deal_eligible and best_snack.meal_deal_eligible and best_drink.meal_deal_eligible:
            d = shop_deals[0]
            dp = d.loyalty_price_gbp if (prefs.has_clubcard or prefs.has_nectar) and d.loyalty_price_gbp else d.price_gbp
            if dp < sep_price and dp <= p_max:
                price, used_deal, deal_obj = dp, True, d

        results.append(Lunch(
            shop=shop,
            main=main,
            snack=best_snack,
            drink=best_drink,
            price_gbp=price,
            used_deal=used_deal,
            deal=deal_obj,
            score=score_lunch(main, best_snack, best_drink, price, prefs),
        ))

    return results


def get_results(
    shops: list[Shop],
    items: list[Item],
    deals: list[Deal],
    prefs: Preferences,
    today: date | None = None,
) -> tuple[Optional[Lunch], list[Lunch], list[Lunch]]:
    """
    Three-section results as per PLAN.md:

    Returns:
        primary       — single best Lunch, or None if no results
        alternatives  — up to 3 more Lunches at primary.shop (varying main)
        other_shops   — best Lunch from the next 3 ranked shops
    """
    ranked = rank_shops(shops, items, deals, prefs, today)

    if not ranked:
        return None, [], []

    primary = ranked[0]

    # Section B: alternatives at primary shop (skip the primary main)
    all_at_primary = top_lunches_for_shop(primary.shop, items, deals, prefs, n=4)
    alternatives = [l for l in all_at_primary if l.main.item_id != primary.main.item_id][:3]

    # Section C: best from next 3 shops
    other_shops = ranked[1:4]

    return primary, alternatives, other_shops


def generate_why(lunch: Lunch, all_lunches: list[Lunch]) -> str:
    """
    Ask Claude to write a one-line explanation for why this shop ranks where it does.
    Only uses fields already in the result — never adds allergen or diet judgements.
    """
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()

    rank = next(
        (i + 1 for i, l in enumerate(all_lunches) if l.shop.shop_id == lunch.shop.shop_id),
        "?",
    )

    prompt = f"""
Write a single short sentence (max 12 words) explaining why this shop ranks #{rank} for lunch.
Use only the facts below. Do not mention allergens, diet flags, or inferences.

Shop: {lunch.shop.name}
Price: £{lunch.price_gbp:.2f} {'(meal deal)' if lunch.used_deal else '(separate)'}
Main: {lunch.main.name} ({'hot' if lunch.main.temperature == 'hot' else 'cold/ambient'})
Score: {lunch.score:.3f}
Walking: {lunch.shop.walking_minutes} min

Respond with only the sentence, no punctuation at the end.
"""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
