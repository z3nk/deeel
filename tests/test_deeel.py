"""Tests for deeel.py and the Deeel sort in the optimiser."""

import time

from deeel import WEIGHTS, deeel_score, ingredient_score
from models import Preferences
from optimiser import best_lunch_for_shop, get_results, lunch_deeel
from tests.test_optimiser import SHOP_A, TODAY, _deal, _item


def _trio(**main_kw):
    main = _item("m", "shop-a", "main", 3.00, kcal=500, protein_g=30, **main_kw)
    snack = _item("s", "shop-a", "snack", 1.00, kcal=100, protein_g=2)
    drink = _item("d", "shop-a", "drink", 1.00, kcal=0, protein_g=0)
    return main, snack, drink


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_score_in_range_and_complete_when_known():
    m, s, d = _trio()
    score = deeel_score(m, s, d, price_gbp=5.0, separate_price_gbp=5.0)
    assert 0 <= score.total <= 100
    assert set(score.parts) == set(WEIGHTS)
    assert score.partial  # no ingredients text → ingredient quality unknown


def test_cheaper_scores_higher():
    m, s, d = _trio()
    assert deeel_score(m, s, d, 4.0, 5.0).exact > deeel_score(m, s, d, 5.0, 5.0).exact


def test_unknown_nutrition_is_neutral_and_partial():
    m = _item("m", "shop-a", "main", 3.00)
    s = _item("s", "shop-a", "snack", 1.00)
    d = _item("d", "shop-a", "drink", 1.00)
    score = deeel_score(m, s, d, 5.0, 5.0)
    assert score.parts["filling"] == 0.5 and score.parts["balance"] == 0.5
    assert score.partial


def test_ingredients_penalise_e_numbers():
    clean = _item("c", "shop-a", "main", 3.0).model_copy(update={"ingredients_text": "Chicken, bread, lettuce"})
    additive = _item("a", "shop-a", "main", 3.0).model_copy(
        update={"ingredients_text": "Chicken, bread, E330, E211, E202, E471, E472e, lettuce"})
    assert ingredient_score(clean)[0] > ingredient_score(additive)[0]
    assert ingredient_score(_item("u", "shop-a", "main", 3.0)) == (0.4, False)


def test_deeel_sort_prefers_filling_value_combo():
    """Deeel picks the protein-rich main even though the other main is cheaper by 20p."""
    items = [
        _item("salad", "shop-a", "main",  2.80, kcal=250, protein_g=6),
        _item("chick", "shop-a", "main",  3.00, kcal=480, protein_g=32),
        _item("crisp", "shop-a", "snack", 1.00, kcal=130, protein_g=2),
        _item("water", "shop-a", "drink", 0.90, kcal=0,   protein_g=0),
    ]
    lunch = best_lunch_for_shop(SHOP_A, items, [], Preferences(sort="deeel"))
    assert lunch.main.item_id == "chick"
    assert lunch.score == lunch_deeel(lunch, Preferences(sort="deeel")).exact


def test_deeel_sort_uses_deal_when_cheaper():
    items = [
        _item("m", "shop-a", "main",  3.00, kcal=480, protein_g=30),
        _item("s", "shop-a", "snack", 1.50, kcal=130, protein_g=2),
        _item("d", "shop-a", "drink", 1.50, kcal=0,   protein_g=0),
    ]
    lunch = best_lunch_for_shop(SHOP_A, items, [_deal("deal", "shop-a", 4.00)], Preferences(sort="deeel"))
    assert lunch.used_deal and lunch.price_gbp == 4.00


def test_deeel_search_is_fast_on_a_big_shop():
    items = [
        _item(f"{cat}{n}", "shop-a", cat, 1.0 + n * 0.1, kcal=100 + n * 20, protein_g=n)
        for cat in ("main", "snack", "drink") for n in range(30)
    ]
    start = time.perf_counter()
    primary, alts, _ = get_results([SHOP_A], items, [], Preferences(sort="deeel", max_price_gbp=14), today=TODAY)
    assert primary is not None and len(alts) == 3
    assert time.perf_counter() - start < 0.5
