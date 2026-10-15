"""
Ingredient quality: how processed an item is, read from its printed ingredients list.

Method (based on the NOVA idea that ultra-processed foods are marked by
industrial additives and ingredients you wouldn't cook with at home):

1. Additive TYPES, not additive count. Each marker type present costs points once,
   whether it's written as an E-number (E471) or by name ("emulsifier",
   "mono- and diglycerides"). Counting types stops one long label of near-identical
   additives from dominating, and catches labels that never use E-numbers.
2. Benign additives are ignored: antioxidants and acids in E300–E399
   (vitamin C, citric acid, lecithin) and E500s (acidity regulators, raising agents).
3. Top-level ingredient count. Sub-ingredients inside brackets don't count, so
   "Bread (wheat flour, water, yeast)" is one ingredient — sandwiches aren't punished
   for listing what's in their bread.
4. Unknown (no ingredients printed / unreadable) scores UNKNOWN_SCORE, which is below an
   average label, so a missing label never beats an honest one.

Not used: premium-range branding (marketing, not ingredients) or student ratings
(taste, not ingredients) — those feed the Quality sort instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

UNKNOWN_SCORE = 0.4
PENALTY_PER_TYPE = 0.12      # per ultra-processing marker type present
MAX_TYPE_PENALTY = 0.6
FREE_INGREDIENTS = 6         # top-level ingredients allowed before the length penalty
PENALTY_PER_EXTRA = 0.03
MAX_LENGTH_PENALTY = 0.3

# Marker type → (E-number ranges, name patterns). Names cover UK and US spelling.
MARKERS: dict[str, tuple[list[tuple[int, int]], list[str]]] = {
    "colours": ([(100, 199)], [r"colou?rs?\b", r"carmine", r"tartrazine"]),
    "preservatives": ([(200, 299)], [r"preservatives?", r"sorbate", r"benzoate", r"nitrite",
                                     r"nitrate", r"sulph?ite", r"sulph?ur dioxide", r"propionate"]),
    "emulsifiers & thickeners": ([(400, 499)], [r"emulsifiers?", r"stabili[sz]ers?", r"thickeners?",
                                               r"gelling agent", r"xanthan", r"guar gum", r"carrageenan",
                                               r"mono- ?and di-?glycerides", r"polysorbate", r"cellulose gum"]),
    "flavour enhancers": ([(600, 699)], [r"flavou?r enhancers?", r"monosodium glutamate", r"\bmsg\b",
                                         r"disodium (?:inosinate|guanylate|ribonucleotides)"]),
    "sweeteners": ([(950, 969)], [r"sweeteners?", r"aspartame", r"sucralose", r"acesulfame",
                                  r"saccharin", r"steviol", r"sorbitol", r"maltitol", r"xylitol"]),
    "modified starch": ([(1400, 1499)], [r"modified (?:\w+ )?starch"]),
    "flavourings": ([], [r"flavou?rings?\b"]),
    "syrups & refined sugars": ([], [r"glucose(?:-fructose)? syrup", r"fructose syrup",
                                     r"invert sugar", r"dextrose", r"maltodextrin", r"corn syrup"]),
    "hydrogenated fats": ([], [r"hydrogenated"]),
}

_E_NUMBER = re.compile(r"\bE ?(\d{3,4})[a-z]?\b", re.IGNORECASE)
_STOP_AT = re.compile(r"\b(?:may contain|allergy advice|for allergens|allergens:)", re.IGNORECASE)
_PREFIX = re.compile(r"^\s*ingredients\s*:\s*", re.IGNORECASE)
_NAME_PATTERNS = {
    kind: re.compile("|".join(names), re.IGNORECASE)
    for kind, (_, names) in MARKERS.items() if names
}


@dataclass
class IngredientAssessment:
    score: float                                     # 0–1
    known: bool                                      # False = no ingredients on label
    markers: list[str] = field(default_factory=list) # ultra-processing marker types found
    n_ingredients: int = 0                           # top-level ingredients

    def reason(self) -> str:
        if not self.known:
            return "no ingredients on label"
        parts = [f"{self.n_ingredients} ingredient{'s' if self.n_ingredients != 1 else ''}"]
        parts.append(", ".join(self.markers) if self.markers else "no processing markers")
        return " · ".join(parts)


def _clean(text: str) -> str:
    text = _PREFIX.sub("", text)
    stop = _STOP_AT.search(text)
    return text[: stop.start()] if stop else text


def top_level_ingredients(text: str) -> list[str]:
    """Split on commas/semicolons outside brackets: 'Bread (flour, water), Ham' → 2."""
    items, depth, current = [], 0, []
    for ch in _clean(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [i.strip(" .\n\t") for i in items if i.strip(" .\n\t")]


def marker_types(text: str) -> list[str]:
    """Ultra-processing marker types present, by E-number range or by name."""
    text = _clean(text)
    numbers = [int(n) for n in _E_NUMBER.findall(text)]
    found = []
    for kind, (ranges, _) in MARKERS.items():
        by_number = any(lo <= n <= hi for n in numbers for lo, hi in ranges)
        by_name = kind in _NAME_PATTERNS and _NAME_PATTERNS[kind].search(text)
        if by_number or by_name:
            found.append(kind)
    return found


def assess(ingredients_text: str | None) -> IngredientAssessment:
    if not ingredients_text or not ingredients_text.strip():
        return IngredientAssessment(score=UNKNOWN_SCORE, known=False)
    markers = marker_types(ingredients_text)
    n = len(top_level_ingredients(ingredients_text))
    type_penalty = min(MAX_TYPE_PENALTY, PENALTY_PER_TYPE * len(markers))
    length_penalty = min(MAX_LENGTH_PENALTY, PENALTY_PER_EXTRA * max(0, n - FREE_INGREDIENTS))
    score = max(0.0, 1.0 - type_penalty - length_penalty)
    return IngredientAssessment(score=score, known=True, markers=markers, n_ingredients=n)
