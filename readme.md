# Deeelicious

A lunch optimiser for UCL Bloomsbury students. Set your preferences, and Deeelicious finds the best main + snack + drink combo across nearby shops — comparing meal deals against buying separately.

## How it works

1. **Capture** — Upload a shelf-label photo. Claude Vision extracts the item name, price, diet flags and allergens into structured data.
2. **Search** — The optimiser filters by your diet, allergens, budget, walking distance and freshness, then scores every possible lunch with a weighted formula.
3. **Results** — One featured recommendation, up to 3 alternatives at the same shop, and the best option from 3 other nearby shops.

## Features

- **Sidebar preferences** — Max price, walking limit, hot/cold/any, diet chips (vegetarian, vegan, halal, kosher), meat-in-main chips, whole-meal protein / calorie limits, allergen exclusions, loyalty cards (Clubcard / Nectar), sort by Deeel score / quality / distance / price.
- **Deeel score** — Every combination gets a 0–100 rating; see below.
- **Live tour** — The **?** button in the top-right walks through the app on live data.
- **Deal vs. separate pricing** — Automatically compares the meal deal bundle price against buying items individually.
- **Map view** — OpenStreetMap with colour-coded shop markers and a walking-radius circle.
- **Credits & rewards** — Earn credits for approved photo submissions; redeem them for sponsor vouchers.
- **Freshness tracking** — Every price carries a `last_seen` date and links back to the source photo. Items older than 14 days are excluded from ranking.

## The Deeel score

A 0–100 rating for each main + snack + drink, built only from label data:

| Factor | Points | How it's scored |
|---|---|---|
| Value | 30 | Meal price on a fixed scale: £3 = full marks, £8 = zero |
| Fillingness | 25 | Total protein (30 g = full) and calories (650 kcal = full) |
| Ingredient quality | 25 | How processed the items are — see below. The main counts double |
| Nutrition balance | 10 | Share of calories from protein (25% = full) |
| Deal saving | 10 | % saved by the meal deal vs buying separately (35% = full) |

### Ingredient quality

Read from the printed ingredients list (`ingredients.py`), based on the NOVA idea that ultra-processed food is marked by industrial additives and ingredients you wouldn't cook with:

- **Processing markers, counted by type** — colours, preservatives, emulsifiers & thickeners, flavour enhancers, sweeteners, modified starch, flavourings, glucose syrups / refined sugars, hydrogenated fats. Each type present costs 12 points (max 60), whether it's written as an E-number or by name. Counting types, not additives, stops one long label dominating and catches labels that never use E-numbers.
- **Benign additives are ignored** — antioxidants and acids (E300–E399, e.g. vitamin C, citric acid) and E500s (raising agents, acidity regulators).
- **Ingredient count, top level only** — the first 6 are free, then 3 points each (max 30). Sub-ingredients in brackets don't count, so "Bread (flour, water, yeast)" is one ingredient.
- **No ingredients on the label scores 40** — below a typical label, so leaving the ingredients out of a photo doesn't pay. (A very processed label can still score lower, down to 10.)
- Premium-range branding and student ratings are **not** used here: they measure marketing and taste, not ingredients.

Each card's **How it's scored** button shows the breakdown and the reason for every item, e.g. "5 ingredients · preservatives, emulsifiers & thickeners".

## Supported shops

Tesco · Sainsbury's · Waitrose · M&S · Lidl · Pret — all within walking distance of UCL's main campus.

## Tech stack

| Component | Tech |
|-----------|------|
| UI | Streamlit |
| Storage | SQLite |
| Data validation | Pydantic |
| Vision extraction | Anthropic SDK (Claude) |
| Map | Folium + streamlit-folium |

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Add your Anthropic API key
cp .env.example .env
# Edit .env with your key

# Run the app
streamlit run app.py
```

## Project structure

```
app.py            Streamlit UI
extract.py        Photo → structured item/deal JSON
optimiser.py      Filters, scoring, per-shop search
deeel.py          Deeel score (0–100)
ingredients.py    Ingredient quality: processing markers + ingredient count
demo.py           Live tour behind the ? button
shop_images.py    Shop logos / storefront photos
map_view.py       Folium map helper
ledger.py         Credit ledger and earning rules
approval.py       Pending/approved/rejected flow
models.py         Pydantic schema (frozen)
db.py             SQLite schema and seed data
seed/             Seed-walk photos
tests/            pytest suite
```

## Data integrity

- Diet flags and allergens come **only** from printed label text — never inferred.
- Items with unknown allergen data are excluded when allergen filters are active.
- Duplicate photos are rejected by image hash.
- EXIF location data is stripped from every upload.
