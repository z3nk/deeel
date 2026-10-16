# Deeelicious

![Deeelicious logo](design/brandkit/logo-full.svg)

**Deeelicious helps UCL students pick the best lunch in under 30 seconds.**  
It ranks main + snack + drink combinations across nearby shops using real shelf photos, meal-deal maths, and a transparent 0–100 Deeel score.

👉 Live demo: https://deeelicious.streamlit.app/

## Hackathon pitch

- **Problem:** lunch choices are slow, unclear, and allergy-sensitive.
- **Solution:** one ranked best basket, plus fast alternatives.
- **Data:** hand-collected shelf photos + label-first extraction.
- **Trust:** allergen warning everywhere; unknown is treated as unsafe.
- **Incentive loop:** students upload photos, credits pay out only after approval.

## What users can control

- Budget, walking time, and sort mode (Deeel score / quality / distance / price)
- Diet and main-meat filters
- Allergen filters (label-first safety logic)
- Whole-meal protein and calorie limits
- Hot/cold preference and loyalty-card pricing toggles

## What users see

- **Section A:** one featured best option
- **Section B:** up to 3 alternatives at the same shop
- **Section C:** up to 3 options at other shops
- **Map tab:** ranked shop markers and walking radius

## Safety + data rules

- Diet flags come from printed labels only.
- Allergens come from printed labels; barcode fill can add exclusions.
- Open Food Facts can exclude items but never clear allergen risk.
- Stale items (>14 days) are excluded from ranking and shown separately.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

For developer setup, tests, and architecture notes, see [`dev.md`](dev.md).
