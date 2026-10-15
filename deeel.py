"""
Deeel score: a 0–100 rating for one main + snack + drink combination.

Weighted sum of factors, each scored 0–1 from label data only:
    value        cheap on a fixed £ scale (comparable across users' price caps)
    filling      total protein + kcal
    ingredients  how processed the items are, from printed ingredients (see ingredients.py)
    balance      share of calories from protein
    deal         % saved by the meal deal versus buying separately

Unknown nutrition scores a neutral 0.5; unknown ingredients score ingredients.UNKNOWN_SCORE.
Either way the result is marked partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ingredients import assess
from models import Item

WEIGHTS = {
    "value": 30,
    "filling": 25,
    "ingredients": 25,
    "balance": 10,
    "deal": 10,
}
LABELS = {
    "value": "Value",
    "filling": "Fillingness",
    "ingredients": "Ingredient quality",
    "balance": "Nutrition balance",
    "deal": "Deal saving",
}

PRICE_BEST, PRICE_WORST = 3.0, 8.0      # £ for a whole meal
PROTEIN_FULL = 30.0                     # g for full marks
KCAL_FULL = 650.0                       # kcal for full marks
PROTEIN_SHARE_FULL = 0.25               # 25% of kcal from protein = full marks
SAVING_FULL = 0.35                      # 35% off separate price = full marks
NEUTRAL = 0.5

@dataclass
class DeeelScore:
    total: int                                   # 0–100, for display
    exact: float = 0.0                           # unrounded, for ranking
    parts: dict[str, float] = field(default_factory=dict)   # factor → 0–1
    partial: bool = False                        # some inputs unknown


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def ingredient_score(item: Item) -> tuple[float, bool]:
    """(0–1, known) for one item, from its printed ingredients only."""
    a = assess(item.ingredients_text)
    return a.score, a.known


def deeel_score(
    main: Item,
    snack: Item,
    drink: Item,
    price_gbp: float,
    separate_price_gbp: float | None,
) -> DeeelScore:
    trio = (main, snack, drink)
    partial = False
    parts: dict[str, float] = {}

    parts["value"] = _clamp((PRICE_WORST - price_gbp) / (PRICE_WORST - PRICE_BEST))

    kcal_known = all(i.kcal is not None for i in trio)
    protein_known = all(i.protein_g is not None for i in trio)
    kcal = sum(i.kcal for i in trio) if kcal_known else None
    protein = sum(i.protein_g for i in trio) if protein_known else None

    if kcal is not None and protein is not None:
        parts["filling"] = 0.6 * _clamp(protein / PROTEIN_FULL) + 0.4 * _clamp(kcal / KCAL_FULL)
        parts["balance"] = _clamp((protein * 4 / kcal) / PROTEIN_SHARE_FULL) if kcal else 0.0
    else:
        partial = True
        parts["filling"] = NEUTRAL
        parts["balance"] = NEUTRAL

    # Main counts double: it's most of the meal
    scored = [ingredient_score(i) for i in trio]
    parts["ingredients"] = (2 * scored[0][0] + scored[1][0] + scored[2][0]) / 4
    if not all(known for _, known in scored):
        partial = True

    if separate_price_gbp is None:          # deal-only item in the meal: saving unknown
        parts["deal"] = NEUTRAL
        partial = True
    else:
        saving = (separate_price_gbp - price_gbp) / separate_price_gbp if separate_price_gbp > 0 else 0.0
        parts["deal"] = _clamp(saving / SAVING_FULL)

    total = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
    return DeeelScore(total=round(total), exact=total, parts=parts, partial=partial)
