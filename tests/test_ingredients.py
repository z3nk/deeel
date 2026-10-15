"""Tests for ingredients.py — the ingredient quality part of the Deeel score."""

from ingredients import UNKNOWN_SCORE, assess, marker_types, top_level_ingredients

SANDWICH = (
    "Ingredients: Malted Bread (Wheat Flour, Water, Malted Wheat Flakes, Yeast, Salt, "
    "Emulsifier (E471), Flour Treatment Agent (Ascorbic Acid)), Cooked Chicken (24%), "
    "Mayonnaise (Rapeseed Oil, Water, Pasteurised Egg Yolk, Spirit Vinegar, Sugar, Salt, "
    "Stabiliser (Xanthan Gum), Preservative (Potassium Sorbate)), Lettuce. "
    "For allergens, see ingredients in bold. May contain sesame."
)
COKE = ("Carbonated Water, Sugar, Colour (Caramel E150d), Phosphoric Acid, "
        "Natural Flavourings Including Caffeine")


def test_brackets_dont_count_as_extra_ingredients():
    assert top_level_ingredients(SANDWICH) == [
        "Malted Bread (Wheat Flour, Water, Malted Wheat Flakes, Yeast, Salt, "
        "Emulsifier (E471), Flour Treatment Agent (Ascorbic Acid))",
        "Cooked Chicken (24%)",
        "Mayonnaise (Rapeseed Oil, Water, Pasteurised Egg Yolk, Spirit Vinegar, Sugar, Salt, "
        "Stabiliser (Xanthan Gum), Preservative (Potassium Sorbate))",
        "Lettuce",
    ]


def test_allergy_footer_is_ignored():
    assert "sesame" not in " ".join(top_level_ingredients(SANDWICH)).lower()


def test_marker_types_counted_once_each():
    # E471 + "Emulsifier" + "Stabiliser" + "Xanthan" are all one type
    assert marker_types(SANDWICH) == ["preservatives", "emulsifiers & thickeners"]


def test_markers_by_name_without_e_numbers():
    assert marker_types("Water, Sugar, Sweeteners (Sucralose), Natural Flavouring") == [
        "sweeteners", "flavourings"]
    assert marker_types("Potato, Oil, Monosodium Glutamate") == ["flavour enhancers"]
    assert marker_types("Chicken, Modified Maize Starch") == ["modified starch"]
    assert marker_types("Wheat flour, E1422") == ["modified starch"]


def test_benign_additives_ignored():
    assert marker_types("Orange Juice, Antioxidant (Ascorbic Acid), E330, E300, E500") == []


def test_coke_markers():
    assert marker_types(COKE) == ["colours", "flavourings"]


def test_whole_food_scores_full():
    a = assess("Banana")
    assert a.known and a.score == 1.0 and a.reason() == "1 ingredient · no processing markers"


def test_unknown_scores_below_typical_label():
    unknown = assess(None)
    assert not unknown.known and unknown.score == UNKNOWN_SCORE
    assert assess(SANDWICH).score > unknown.score   # an honest sandwich label beats no label


def test_ultra_processed_scores_lower_than_simple():
    simple = assess("Chicken, Bread (Wheat Flour, Water, Yeast, Salt), Lettuce, Mayonnaise")
    upf = assess("Chicken, Bread, Emulsifier (E471), Preservative (E202), Colour (E150d), "
                 "Sweetener (Sucralose), Flavouring, Glucose Syrup, Modified Starch, Hydrogenated Palm Oil")
    assert simple.score > upf.score
    # 8 marker types → penalty capped at 0.6; 10 ingredients → 4 extra × 0.03
    assert abs(upf.score - (1 - 0.6 - 0.12)) < 1e-9
    assert len(upf.markers) == 8


def test_no_false_positives_on_plain_words():
    assert marker_types("Tomatoes, Water, Colourful Peppers, Onion, Basil") == []
