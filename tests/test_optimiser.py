"""
Tests for optimiser.py.
Uses 3 invented shops with hardcoded items — no DB, no API needed.
"""

from datetime import date

import pytest

from models import Deal, Item, Preferences, Shop
from optimiser import best_lunch_for_shop, get_results, hard_filter, rank_shops, score_lunch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TODAY = date(2026, 10, 12)
FRESH = "2026-10-10"   # 2 days ago — within STALE_DAYS
STALE = "2026-09-01"   # >14 days ago — filtered out


def _shop(shop_id: str, walking: float) -> Shop:
    return Shop(
        shop_id=shop_id,
        chain="tesco",
        name=f"Shop {shop_id}",
        address="Test Street",
        walking_minutes=walking,
        last_verified=TODAY,
        lat=51.52,
        lng=-0.13,
    )


def _item(
    item_id: str,
    shop_id: str,
    category: str,
    price: float,
    temperature: str = "cold",
    diet_flags: list[str] | None = None,
    allergens: list[str] | None = None,
    meal_deal_eligible: bool | None = True,
    last_seen: str = FRESH,
    status: str = "approved",
    quality_rating: float | None = None,
    meats: list[str] | None = None,
    kcal: float | None = None,
    protein_g: float | None = None,
) -> Item:
    return Item(
        item_id=item_id,
        shop_id=shop_id,
        name=f"Item {item_id}",
        category=category,
        price_gbp=price,
        temperature=temperature,
        diet_flags=diet_flags or [],
        allergens=allergens or [],
        meal_deal_eligible=meal_deal_eligible,
        source_image="test.jpg",
        source_text="test",
        last_seen=last_seen,
        submitted_via="seed",
        status=status,
        quality_rating=quality_rating,
        meats=meats,
        kcal=kcal,
        protein_g=protein_g,
    )


def _deal(deal_id: str, shop_id: str, price: float) -> Deal:
    return Deal(
        deal_id=deal_id,
        shop_id=shop_id,
        name="Meal Deal",
        price_gbp=price,
        source_image="deal.jpg",
        last_seen=TODAY,
        status="approved",
    )


# ---------------------------------------------------------------------------
# Three invented shops for ranking tests
#
# Shop A: cheapest items (£2 each = £6 sep), has a deal at £4.25
# Shop B: more expensive items (£3 each = £9 sep), no deal
# Shop C: has a hot main, moderate price (£2.50 each = £7.50 sep)
# ---------------------------------------------------------------------------

SHOP_A = _shop("shop-a", walking=4.0)
SHOP_B = _shop("shop-b", walking=6.0)
SHOP_C = _shop("shop-c", walking=5.0)

ITEMS_A = [
    _item("a-main",  "shop-a", "main",  2.00),
    _item("a-snack", "shop-a", "snack", 2.00),
    _item("a-drink", "shop-a", "drink", 2.00),
]
DEAL_A = _deal("deal-a", "shop-a", 4.25)

ITEMS_B = [
    _item("b-main",  "shop-b", "main",  3.00),
    _item("b-snack", "shop-b", "snack", 3.00),
    _item("b-drink", "shop-b", "drink", 3.00),
]

ITEMS_C = [
    _item("c-main",  "shop-c", "main",  2.50, temperature="hot"),
    _item("c-snack", "shop-c", "snack", 2.50),
    _item("c-drink", "shop-c", "drink", 2.50),
]

ALL_ITEMS = ITEMS_A + ITEMS_B + ITEMS_C
ALL_DEALS = [DEAL_A]
ALL_SHOPS = [SHOP_A, SHOP_B, SHOP_C]


# ---------------------------------------------------------------------------
# hard_filter tests
# ---------------------------------------------------------------------------

class TestHardFilter:
    def test_stale_item_excluded(self):
        stale = _item("stale-1", "shop-a", "main", 2.00, last_seen=STALE)
        prefs = Preferences()
        result = hard_filter([stale], prefs, today=TODAY)
        assert result == []

    def test_fresh_item_included(self):
        fresh = _item("fresh-1", "shop-a", "main", 2.00, last_seen=FRESH)
        prefs = Preferences()
        result = hard_filter([fresh], prefs, today=TODAY)
        assert len(result) == 1

    def test_allergen_exclusion_removes_item(self):
        item = _item("nut-item", "shop-a", "main", 2.00, allergens=["nuts"])
        prefs = Preferences(allergens_exclude=["nuts"])
        result = hard_filter([item], prefs, today=TODAY)
        assert result == []

    def test_null_allergens_excluded_when_filter_set(self):
        """Item with unknown allergens must be excluded if user has allergen needs."""
        item = _item("unknown", "shop-a", "main", 2.00, allergens=[])
        prefs = Preferences(allergens_exclude=["nuts"])
        result = hard_filter([item], prefs, today=TODAY)
        assert result == []

    def test_diet_flag_required(self):
        non_veg = _item("meat", "shop-a", "main", 2.00, diet_flags=[])
        veg = _item("veg", "shop-a", "main", 2.00, diet_flags=["vegetarian"])
        prefs = Preferences(diet_flags=["vegetarian"])
        result = hard_filter([non_veg, veg], prefs, today=TODAY)
        assert [i.item_id for i in result] == ["veg"]

    def test_rejected_item_always_excluded(self):
        item = _item("rej", "shop-a", "main", 2.00, status="rejected")
        prefs = Preferences()
        result = hard_filter([item], prefs, today=TODAY)
        assert result == []


# ---------------------------------------------------------------------------
# rank_shops tests
# ---------------------------------------------------------------------------

class TestRankShops:
    def test_cheapest_first_price_weight_wins(self):
        """With sort='price' → shop-a (deal £4.25) ranks first."""
        prefs = Preferences(sort="price")
        ranked = rank_shops(ALL_SHOPS, ALL_ITEMS, ALL_DEALS, prefs, today=TODAY)
        assert len(ranked) >= 1
        assert ranked[0].shop.shop_id == "shop-a"
        assert ranked[0].used_deal is True
        assert ranked[0].price_gbp == 4.25

    def test_warmest_first_warmth_weight_wins(self):
        """With temperature_pref='hot' → shop-c (hot main) ranks first."""
        prefs = Preferences(temperature_pref="hot")
        ranked = rank_shops(ALL_SHOPS, ALL_ITEMS, ALL_DEALS, prefs, today=TODAY)
        assert len(ranked) >= 1
        assert ranked[0].shop.shop_id == "shop-c"

    def test_allergen_excludes_shop(self):
        """If the only main at shop-a has nuts, shop-a should produce no lunch."""
        items_with_nuts = [
            _item("a-main",  "shop-a", "main",  2.00, allergens=["nuts"]),
            _item("a-snack", "shop-a", "snack", 2.00, allergens=[]),
            _item("a-drink", "shop-a", "drink", 2.00, allergens=[]),
        ] + ITEMS_B + ITEMS_C

        prefs = Preferences(allergens_exclude=["nuts"])
        ranked = rank_shops(ALL_SHOPS, items_with_nuts, ALL_DEALS, prefs, today=TODAY)
        shop_ids = [l.shop.shop_id for l in ranked]
        assert "shop-a" not in shop_ids

    def test_walking_limit_excludes_distant_shop(self):
        """Shop-b at 6 min is excluded when walking limit is 5 min."""
        prefs = Preferences(max_walking_minutes=5.0)
        ranked = rank_shops(ALL_SHOPS, ALL_ITEMS, ALL_DEALS, prefs, today=TODAY)
        shop_ids = [l.shop.shop_id for l in ranked]
        assert "shop-b" not in shop_ids

    def test_deal_beats_separate_when_cheaper(self):
        """Shop-a deal (£4.25) beats separate (£6.00) — used_deal should be True."""
        prefs = Preferences(sort="price")
        ranked = rank_shops(ALL_SHOPS, ALL_ITEMS, ALL_DEALS, prefs, today=TODAY)
        shop_a_lunch = next(l for l in ranked if l.shop.shop_id == "shop-a")
        assert shop_a_lunch.used_deal is True

    def test_separate_beats_deal_when_deal_is_expensive(self):
        """If deal price > sum of items, separate mode should win."""
        expensive_deal = _deal("deal-a2", "shop-a", 10.00)  # deal = £10, separate = £6
        prefs = Preferences(sort="price")
        lunch = best_lunch_for_shop(SHOP_A, ITEMS_A, [expensive_deal], prefs)
        assert lunch is not None
        assert lunch.used_deal is False


# ---------------------------------------------------------------------------
# Meat + nutrition filters
# ---------------------------------------------------------------------------

class TestMeatFilter:
    CHICKEN = _item("chk", "shop-a", "main", 2.00, meats=["chicken"])
    HAM     = _item("ham", "shop-a", "main", 2.00, meats=["pork"])
    VEG     = _item("veg", "shop-a", "main", 2.00, meats=[])
    UNKNOWN = _item("unk", "shop-a", "main", 2.00, meats=None)

    def _ids(self, allowed):
        items = [self.CHICKEN, self.HAM, self.VEG, self.UNKNOWN]
        return [i.item_id for i in hard_filter(items, Preferences(meats_allowed=allowed), today=TODAY)]

    def test_no_filter_keeps_all(self):
        assert self._ids([]) == ["chk", "ham", "veg", "unk"]

    def test_chicken_only(self):
        assert self._ids(["chicken"]) == ["chk"]

    def test_no_meat(self):
        assert self._ids(["none"]) == ["veg"]

    def test_chicken_or_no_meat(self):
        assert self._ids(["chicken", "none"]) == ["chk", "veg"]

    def test_unknown_meat_excluded(self):
        assert "unk" not in self._ids(["pork", "chicken", "none"])

    def test_snacks_unaffected(self):
        snack = _item("s", "shop-a", "snack", 1.00, meats=None)
        assert hard_filter([snack], Preferences(meats_allowed=["none"]), today=TODAY) == [snack]


class TestNutrition:
    ITEMS = [
        _item("big",   "shop-a", "main",  2.00, quality_rating=5, kcal=700, protein_g=40),
        _item("light", "shop-a", "main",  2.00, quality_rating=3, kcal=300, protein_g=20),
        _item("crisp", "shop-a", "snack", 1.00, quality_rating=5, kcal=200, protein_g=2),
        _item("fruit", "shop-a", "snack", 1.00, quality_rating=3, kcal=60,  protein_g=1),
        _item("coke",  "shop-a", "drink", 1.00, quality_rating=5, kcal=200, protein_g=0),
        _item("water", "shop-a", "drink", 1.00, quality_rating=3, kcal=0,   protein_g=0),
    ]

    def test_unknown_nutrition_excluded_when_limit_set(self):
        item = _item("x", "shop-a", "drink", 1.00)
        assert hard_filter([item], Preferences(max_kcal=800), today=TODAY) == []
        assert hard_filter([item], Preferences(), today=TODAY) == [item]

    def test_no_limit_picks_highest_quality(self):
        lunch = best_lunch_for_shop(SHOP_A, self.ITEMS, [], Preferences())
        assert (lunch.main.item_id, lunch.snack.item_id, lunch.drink.item_id) == ("big", "crisp", "coke")

    def test_kcal_cap_is_whole_meal(self):
        """
        Under 800 kcal: big main only fits with fruit + water (score 2.0); the light
        main fits with crisps + coke (score 2.5), so the search picks that trio.
        """
        lunch = best_lunch_for_shop(SHOP_A, self.ITEMS, [], Preferences(max_kcal=800))
        assert (lunch.main.item_id, lunch.snack.item_id, lunch.drink.item_id) == ("light", "crisp", "coke")
        assert lunch.main.kcal + lunch.snack.kcal + lunch.drink.kcal <= 800

    def test_min_protein(self):
        lunch = best_lunch_for_shop(SHOP_A, self.ITEMS, [], Preferences(min_protein_g=35))
        assert lunch.main.item_id == "big"
        assert best_lunch_for_shop(SHOP_A, self.ITEMS, [], Preferences(min_protein_g=50)) is None

    def test_alternatives_respect_limits(self):
        shop_items = self.ITEMS
        _, alts, _ = get_results([SHOP_A], shop_items, [], Preferences(max_kcal=500), today=TODAY)
        for l in alts:
            assert l.main.kcal + l.snack.kcal + l.drink.kcal <= 500


class TestAlternativesFiltered:
    def test_alternatives_respect_allergens(self):
        """Section B must not offer a main the user is allergic to."""
        items = [
            _item("safe",  "shop-a", "main",  2.00, allergens=["milk"]),
            _item("nutty", "shop-a", "main",  2.00, allergens=["nuts"]),
            _item("s",     "shop-a", "snack", 1.00, allergens=["milk"]),
            _item("d",     "shop-a", "drink", 1.00, allergens=["milk"]),
        ]
        primary, alts, _ = get_results([SHOP_A], items, [], Preferences(allergens_exclude=["nuts"]), today=TODAY)
        assert primary.main.item_id == "safe"
        assert all(l.main.item_id != "nutty" for l in alts)
