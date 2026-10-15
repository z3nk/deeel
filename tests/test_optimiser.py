"""
Tests for optimiser.py.
Uses 3 invented shops with hardcoded items — no DB, no API needed.
"""

from datetime import date

import pytest

from models import Deal, Item, Preferences, Shop
from optimiser import best_lunch_for_shop, get_results, hard_filter, rank_shops, score_lunch, _deal_price


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


# ---------------------------------------------------------------------------
# Shop images
# ---------------------------------------------------------------------------

class TestShopImages:
    def test_badge_fallback_for_every_chain(self, tmp_path, monkeypatch):
        import shop_images
        monkeypatch.setattr(shop_images, "LOGO_DIR", tmp_path)
        for chain in ("tesco", "sainsburys", "waitrose", "marks-and-spencer", "lidl", "pret"):
            shop = SHOP_A.model_copy(update={"chain": chain})
            html = shop_images.logo_html(shop)
            assert f'class="dl-shop dl-shop--{chain}' in html                  # token-backed class
            standalone = shop_images.logo_html(shop, standalone=True)          # map popup (iframe)
            assert "var(--" not in standalone and "background:#" in standalone

    def test_logo_file_used_when_present(self, tmp_path, monkeypatch):
        import shop_images
        (tmp_path / "tesco.png").write_bytes(b"\x89PNG fake")
        monkeypatch.setattr(shop_images, "LOGO_DIR", tmp_path)
        assert 'src="data:image/png;base64,' in shop_images.logo_html(SHOP_A)

    def test_kosher_is_a_label_only_diet_flag(self):
        plain = _item("plain", "shop-a", "main", 2.00)
        kosher = _item("k", "shop-a", "main", 2.00, diet_flags=["Kosher"])
        result = hard_filter([plain, kosher], Preferences(diet_flags=["kosher"]), today=TODAY)
        assert [i.item_id for i in result] == ["k"]


class TestLoyaltyCards:
    def test_clubcard_discount_applies_only_when_has_clubcard(self):
        deal = Deal(deal_id="d1", shop_id="tesco-tcr", name="Meal Deal", price_gbp=4.25, loyalty_price_gbp=3.85, loyalty_scheme="Clubcard", source_image="x.jpg", last_seen=TODAY, status="approved")
        assert _deal_price(deal, Preferences(has_clubcard=False)) == 4.25
        assert _deal_price(deal, Preferences(has_clubcard=True)) == 3.85
        assert _deal_price(deal, Preferences(has_nectar=True)) == 4.25

    def test_nectar_discount_applies_only_when_has_nectar(self):
        deal = Deal(deal_id="d2", shop_id="sainsburys-warren-st", name="Meal Deal", price_gbp=4.50, loyalty_price_gbp=3.50, loyalty_scheme="Nectar", source_image="x.jpg", last_seen=TODAY, status="approved")
        assert _deal_price(deal, Preferences(has_nectar=False)) == 4.50
        assert _deal_price(deal, Preferences(has_nectar=True)) == 3.50
        assert _deal_price(deal, Preferences(has_clubcard=True)) == 4.50


# ---------------------------------------------------------------------------
# Deal-only items (no own price; only a meal deal price on the shelf)
# ---------------------------------------------------------------------------

class TestDealOnlyItems:
    ITEMS = [
        _item("deal-main", "shop-a", "main", 0, quality_rating=5),
        _item("own-main",  "shop-a", "main", 3.00, quality_rating=2),
        _item("s",         "shop-a", "snack", 1.00),
        _item("d",         "shop-a", "drink", 1.00),
    ]
    # price 0 placeholder above → make the first truly deal-only
    ITEMS[0] = ITEMS[0].model_copy(update={"price_gbp": None})

    def test_deal_only_main_used_in_deal(self):
        deal = [_deal("deal", "shop-a", 3.85)]
        # Quality sort: the better-rated deal-only main wins, at the deal price
        lunch = best_lunch_for_shop(SHOP_A, self.ITEMS, deal, Preferences(sort="quality"))
        assert lunch.main.item_id == "deal-main" and lunch.used_deal and lunch.price_gbp == 3.85
        # Deeel: same £3.85, but the priced main has a KNOWN saving (£5 → £3.85), so it edges ahead;
        # the deal-only main is still offered as an alternative
        primary, alts, _ = get_results([SHOP_A], self.ITEMS, deal, Preferences(sort="deeel"), today=TODAY)
        assert primary.main.item_id == "own-main" and primary.used_deal
        assert [l.main.item_id for l in alts] == ["deal-main"] and alts[0].price_gbp == 3.85

    def test_deal_only_main_never_bought_separately(self):
        for sort in ("quality", "deeel"):
            lunch = best_lunch_for_shop(SHOP_A, self.ITEMS, [], Preferences(sort=sort))
            assert lunch.main.item_id == "own-main" and not lunch.used_deal and lunch.price_gbp == 5.00

    def test_no_priced_main_and_no_deal_means_no_lunch(self):
        items = [self.ITEMS[0], self.ITEMS[2], self.ITEMS[3]]
        assert best_lunch_for_shop(SHOP_A, items, [], Preferences()) is None

    def test_alternatives_include_deal_only_mains(self):
        _, alts, _ = get_results([SHOP_A], self.ITEMS, [_deal("deal", "shop-a", 3.85)], Preferences(), today=TODAY)
        primary_and_alts = {l.main.item_id for l in alts} | {"deal-main"}
        assert primary_and_alts == {"deal-main", "own-main"}

    def test_deeel_score_partial_when_separate_price_unknown(self):
        from optimiser import lunch_deeel
        only_deal_main = [self.ITEMS[0], self.ITEMS[2], self.ITEMS[3]]
        lunch = best_lunch_for_shop(SHOP_A, only_deal_main, [_deal("deal", "shop-a", 3.85)], Preferences(sort="deeel"))
        d = lunch_deeel(lunch, Preferences())
        assert d.parts["deal"] == 0.5 and d.partial


def test_build_item_requires_price_or_meal_deal():
    from datetime import date as _d
    from extract import build_item
    ok = build_item({"name": "Wrap", "category": "main", "price_gbp": None, "meal_deal_eligible": True,
                     "confidence": "high"}, "shop-a", "x.jpg", _d(2026, 10, 15), None)
    assert ok.price_gbp is None
    with pytest.raises(ValueError):
        build_item({"name": "Wrap", "category": "main", "price_gbp": None, "meal_deal_eligible": None,
                    "confidence": "high"}, "shop-a", "x.jpg", _d(2026, 10, 15), None)


def test_shop_deal_uses_most_frequently_read_sign():
    from optimiser import shop_deal
    deals = [_deal(f"good{i}", "shop-a", 4.25) for i in range(5)] + [_deal("misread", "shop-a", 3.0),
                                                                     _deal("other", "shop-b", 5.0)]
    assert shop_deal(deals, "shop-a").price_gbp == 4.25
    assert shop_deal(deals, "shop-b").price_gbp == 5.0
    assert shop_deal(deals, "shop-c") is None


def test_is_sample_flags_placeholder_meals():
    from optimiser import is_sample
    real = best_lunch_for_shop(SHOP_A, ITEMS_A, [], Preferences())
    assert not is_sample(real)
    placeholder = real.main.model_copy(update={"source_image": "fallback.jpg"})
    assert is_sample(real.model_copy(update={"main": placeholder}))



class TestAllergenSources:
    """Online (Open Food Facts) allergens can exclude an item but never clear it."""

    def _with(self, allergens, source):
        item = _item("x", "shop-a", "main", 2.00, allergens=allergens)
        return item.model_copy(update={"external_fields": {"allergens": source} if source else {}})

    def test_label_allergens_pass_filter(self):
        assert hard_filter([self._with(["milk"], None)], Preferences(allergens_exclude=["nuts"]), today=TODAY)

    def test_same_barcode_label_allergens_pass_filter(self):
        item = self._with(["milk"], "same barcode, another photo")
        assert hard_filter([item], Preferences(allergens_exclude=["nuts"]), today=TODAY)

    def test_off_allergens_never_clear_an_item(self):
        item = self._with(["milk"], "Open Food Facts")
        assert hard_filter([item], Preferences(allergens_exclude=["nuts"]), today=TODAY) == []

    def test_off_allergens_still_exclude(self):
        item = self._with(["nuts"], "Open Food Facts")
        assert hard_filter([item], Preferences(allergens_exclude=["nuts"]), today=TODAY) == []

    def test_no_allergy_filter_shows_everything(self):
        assert hard_filter([self._with(["milk"], "Open Food Facts")], Preferences(), today=TODAY)

