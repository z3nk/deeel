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
from collections import Counter
from datetime import date, timedelta
from typing import Optional

from deeel import DeeelScore, deeel_score, ingredient_score
from openfoodfacts import SOURCE as OFF_SOURCE
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
    d["meats"] = None if d.get("meats") is None else json.loads(d["meats"])
    d["external_fields"] = json.loads(d.get("external_fields") or "{}")
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
    5. Main's meats all in meats_allowed; unknown meats = excluded
    6. kcal / protein known when a nutrition limit is set (totals checked per meal)
    7. (price cap applied at the lunch level, not item level)
    """
    today = today or date.today()
    cutoff = today - timedelta(days=STALE_DAYS)
    allowed_meats = {m.lower() for m in prefs.meats_allowed}
    results = []

    for item in items:
        # 1. Status
        if prefs.allergens_exclude or prefs.diet_flags or allowed_meats:
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

        # 3. Allergens — unknown = unsafe when the user has allergen needs.
        # Allergens from Open Food Facts (crowd-sourced) can mark an item unsafe
        # below, but never make it pass: only printed-label allergens count as known.
        if prefs.allergens_exclude:
            from_label = item.external_fields.get("allergens") != OFF_SOURCE
            if not item.allergens:  # allergens unknown → exclude
                continue
            item_allergens_lower = [a.lower() for a in item.allergens]
            if any(excl.lower() in item_allergens_lower for excl in prefs.allergens_exclude):
                continue
            if not from_label:      # online data says it's clear — not trusted for safety
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

        # 5. Meat — mains only, like diet flags. [] means meat-free ("none")
        if allowed_meats and item.category == "main":
            if item.meats is None:
                continue
            item_meats = {m.lower() for m in item.meats} or {"none"}
            if not item_meats <= allowed_meats:
                continue

        # 6. Nutrition — every item in the meal needs a known value to total it
        if prefs.max_kcal is not None and item.kcal is None:
            continue
        if prefs.min_protein_g is not None and item.protein_g is None:
            continue

        results.append(item)

    return results


# ---------------------------------------------------------------------------
# Whole-meal nutrition constraints
# ---------------------------------------------------------------------------

def _has_nutrition_limit(prefs: Preferences) -> bool:
    return prefs.max_kcal is not None or prefs.min_protein_g is not None


def _meal_nutrition_ok(main: Item, snack: Item, drink: Item, prefs: Preferences) -> bool:
    trio = (main, snack, drink)
    if prefs.max_kcal is not None and sum(i.kcal for i in trio) > prefs.max_kcal:
        return False
    if prefs.min_protein_g is not None and sum(i.protein_g for i in trio) < prefs.min_protein_g:
        return False
    return True


def _best_sides(main, snacks, drinks, prefs, key) -> Optional[tuple[Item, Item]]:
    """Best (snack, drink) for a fixed main, honouring whole-meal nutrition limits."""
    if not _has_nutrition_limit(prefs):
        return max(snacks, key=key), max(drinks, key=key)
    pairs = [
        (s, d) for s in snacks for d in drinks
        if _meal_nutrition_ok(main, s, d, prefs)
    ]
    if not pairs:
        return None
    return max(pairs, key=lambda p: key(p[0]) + key(p[1]))


def _best_trio(mains, snacks, drinks, prefs, key) -> Optional[tuple[Item, Item, Item]]:
    """
    Highest-scoring main + snack + drink. Without nutrition limits the score is
    additive, so each slot is picked independently; with limits, search per main
    (shops hold a handful of items, so this stays cheap).
    """
    if not _has_nutrition_limit(prefs):
        return max(mains, key=key), max(snacks, key=key), max(drinks, key=key)
    best, best_score = None, float("-inf")
    for m in mains:
        sides = _best_sides(m, snacks, drinks, prefs, key)
        if sides is None:
            continue
        score = key(m) + key(sides[0]) + key(sides[1])
        if score > best_score:
            best, best_score = (m, *sides), score
    return best


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
        "deeel":    (1.0, 1.0, 1.0),   # unused for ranking — deeel sort has its own search
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


def _effective_price(item: Item, prefs: Preferences) -> Optional[float]:
    """The item's own price (loyalty price if the user has a card). None = deal-only."""
    if prefs.has_clubcard and item.loyalty_price_gbp is not None:
        return item.loyalty_price_gbp
    if prefs.has_nectar and item.loyalty_price_gbp is not None:
        return item.loyalty_price_gbp
    return item.price_gbp


def _separate_price(items, prefs: Preferences) -> Optional[float]:
    """Total bought separately, or None if any item is deal-only."""
    prices = [_effective_price(i, prefs) for i in items]
    return None if any(p is None for p in prices) else sum(prices)


def _price_or_inf(item: Item, prefs: Preferences) -> float:
    """Sort key: deal-only items (no own price) go last."""
    price = _effective_price(item, prefs)
    return float("inf") if price is None else price


def _priced(items: list[Item], prefs: Preferences) -> list[Item]:
    return [i for i in items if _effective_price(i, prefs) is not None]


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
# Deeel-score search
# ---------------------------------------------------------------------------

DEEEL_SHORTLIST = 4   # per category, per criterion (cheapest / best ingredients / most protein)


SAMPLE_IMAGE = "fallback.jpg"   # placeholder rows from seed/load_seed.py FALLBACK_ITEMS


def is_sample(lunch: Lunch) -> bool:
    """True if any item in the meal is placeholder (sample) data, not from a real photo."""
    return any(i.source_image == SAMPLE_IMAGE for i in (lunch.main, lunch.snack, lunch.drink))


def shop_deal(deals: list[Deal], shop_id: str) -> Optional[Deal]:
    """
    The shop's meal deal. A sign is usually photographed many times, with the odd
    misread, so take the most frequently seen (name, price, card price); ties → the
    most recently seen. Standard "Meal Deal" beats "Premium Meal Deal".
    """
    candidates = [d for d in deals if d.shop_id == shop_id]
    if not candidates:
        return None
    standard = [d for d in candidates if d.name == "Meal Deal"] or candidates
    counts = Counter((d.name, d.price_gbp, d.loyalty_price_gbp) for d in standard)
    return max(standard, key=lambda d: (counts[(d.name, d.price_gbp, d.loyalty_price_gbp)], str(d.last_seen)))


def _deal_price(deal: Deal, prefs: Preferences) -> float:
    if (prefs.has_clubcard or prefs.has_nectar) and deal.loyalty_price_gbp:
        return deal.loyalty_price_gbp
    return deal.price_gbp


def lunch_deeel(lunch: Lunch, prefs: Preferences) -> DeeelScore:
    """Deeel score for an already-built Lunch (used by the UI for every sort mode)."""
    sep = _separate_price((lunch.main, lunch.snack, lunch.drink), prefs)
    return deeel_score(lunch.main, lunch.snack, lunch.drink, lunch.price_gbp, sep)


def _shortlist(items: list[Item], prefs: Preferences) -> list[Item]:
    """
    Deeel isn't additive per item (fillingness and price are whole-meal), so we
    search combinations — but only over a shortlist to keep reruns instant.
    """
    if len(items) <= DEEEL_SHORTLIST * 2:
        return items
    picks: dict[str, Item] = {}
    rankings = [
        sorted(items, key=lambda i: _price_or_inf(i, prefs)),
        sorted(items, key=lambda i: -ingredient_score(i)[0]),
        sorted(items, key=lambda i: -(i.protein_g or 0)),
    ]
    for ranking in rankings:
        for item in ranking[:DEEEL_SHORTLIST]:
            picks[item.item_id] = item
    return list(picks.values())


def _deeel_lunch(shop, main, snack, drink, deal, prefs) -> Optional[Lunch]:
    """Build a Lunch for this trio at its cheapest price, or None if over the cap/limits."""
    if _has_nutrition_limit(prefs) and not _meal_nutrition_ok(main, snack, drink, prefs):
        return None
    sep = _separate_price((main, snack, drink), prefs)
    price, used_deal, deal_obj = sep, False, None
    if deal is not None and main.meal_deal_eligible and snack.meal_deal_eligible and drink.meal_deal_eligible:
        dp = _deal_price(deal, prefs)
        if sep is None or dp < sep:
            price, used_deal, deal_obj = dp, True, deal
    if price is None or price > (prefs.max_price_gbp or P_MAX_DEFAULT):
        return None
    return Lunch(
        shop=shop, main=main, snack=snack, drink=drink,
        price_gbp=price, used_deal=used_deal, deal=deal_obj,
        score=deeel_score(main, snack, drink, price, sep).exact,
    )


def _deeel_lunches_by_main(shop, mains, snacks, drinks, deals, prefs) -> list[Lunch]:
    """Best Deeel lunch for each main at this shop, best first."""
    deal = shop_deal(deals, shop.shop_id)
    snacks, drinks = _shortlist(snacks, prefs), _shortlist(drinks, prefs)
    results = []
    for main in mains:
        best = None
        for snack in snacks:
            for drink in drinks:
                lunch = _deeel_lunch(shop, main, snack, drink, deal, prefs)
                if lunch is not None and (best is None or lunch.score > best.score):
                    best = lunch
        if best is not None:
            results.append(best)
    results.sort(key=lambda l: -l.score)
    return results


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

    if prefs.sort == "deeel":
        ranked = _deeel_lunches_by_main(shop, _shortlist(mains, prefs), snacks, drinks, deals, prefs)
        return ranked[0] if ranked else None

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

    key = lambda i: _item_score(i, prefs)
    # Separate mode can only use items with their own price (deal-only items excluded)
    p_mains, p_snacks, p_drinks = _priced(mains, prefs), _priced(snacks, prefs), _priced(drinks, prefs)
    trio = _best_trio(p_mains, p_snacks, p_drinks, prefs, key) if p_mains and p_snacks and p_drinks else None
    sep_price = _separate_price(trio, prefs) if trio else None

    if trio is not None and sep_price <= p_max:
        best_main, best_snack, best_drink = trio
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
    deal = shop_deal(deals, shop.shop_id)
    if deal is not None:
        deal_price = (
            deal.loyalty_price_gbp
            if (prefs.has_clubcard or prefs.has_nectar) and deal.loyalty_price_gbp
            else deal.price_gbp
        )

        deal_mains  = [i for i in mains  if i.meal_deal_eligible]
        deal_snacks = [i for i in snacks if i.meal_deal_eligible]
        deal_drinks = [i for i in drinks if i.meal_deal_eligible]

        deal_trio = (
            _best_trio(deal_mains, deal_snacks, deal_drinks, prefs, key)
            if deal_mains and deal_snacks and deal_drinks and deal_price <= p_max
            else None
        )
        if deal_trio is not None:
            dm, ds, dd = deal_trio
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

    if prefs.sort == "deeel":
        return _deeel_lunches_by_main(shop, mains, snacks, drinks, deals, prefs)[:n]

    p_max = prefs.max_price_gbp or P_MAX_DEFAULT
    the_deal = shop_deal(deals, shop.shop_id)

    def _item_score(item: Item) -> float:
        w_p, w_q, w_h = _weights_from_sort(prefs)
        return w_q * _quality_score(item) + (w_h if item.temperature == "hot" and item.category == "main" else 0)

    # Rank all mains and produce one Lunch per main, each with its best sides
    # (the same snack + drink unless nutrition limits force a different pair)
    ranked_mains = sorted(mains, key=_item_score, reverse=True)
    results: list[Lunch] = []

    def _priced_lunch(main, best_snack, best_drink):
        """(price, used_deal, deal) for this trio, or None if it can't be bought within the cap."""
        sep_price = _separate_price((main, best_snack, best_drink), prefs)
        price, used_deal, deal_obj = sep_price, False, None
        if the_deal and main.meal_deal_eligible and best_snack.meal_deal_eligible and best_drink.meal_deal_eligible:
            d = the_deal
            dp = d.loyalty_price_gbp if (prefs.has_clubcard or prefs.has_nectar) and d.loyalty_price_gbp else d.price_gbp
            if (sep_price is None or dp < sep_price) and dp <= p_max:
                price, used_deal, deal_obj = dp, True, d
        return None if price is None or price > p_max else (price, used_deal, deal_obj)

    deal_snacks = [i for i in snacks if i.meal_deal_eligible]
    deal_drinks = [i for i in drinks if i.meal_deal_eligible]

    for main in ranked_mains:
        if len(results) == n:
            break
        # Best sides overall; if that trio can't be priced (e.g. a deal-only side
        # with a main outside the deal), fall back to deal-eligible sides
        priced = None
        for pool_s, pool_d in ((snacks, drinks), (deal_snacks, deal_drinks)):
            if not pool_s or not pool_d:
                continue
            sides = _best_sides(main, pool_s, pool_d, prefs, _item_score)
            if sides and (priced := _priced_lunch(main, *sides)):
                best_snack, best_drink = sides
                break
        if not priced:
            continue
        price, used_deal, deal_obj = priced

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
    # Must use filtered items, or alternatives would ignore allergen/diet/meat filters
    filtered_items = hard_filter(items, prefs, today)
    all_at_primary = top_lunches_for_shop(primary.shop, filtered_items, deals, prefs, n=4)
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
