# Deeelicious

A lunch optimiser for UCL Bloomsbury students. Set your preferences, and Deeelicious finds the best main + snack + drink combo across nearby shops — comparing meal deals against buying separately.

The app is live at [https://deeelicious.streamlit.app/](https://deeelicious.streamlit.app/).

## How it works

1. **Capture** — Pick the shop and photo type (main / snack / drink / general), upload one or many photos. Claude Vision reads every product in each photo (a whole shelf works) plus any meal deal sign; you check and edit them in a table before submitting for approval.
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

## Importing a batch of photos (seed walk)

Instead of the upload screen, drop photos into folders and run one command:

```
seed/inbox/<shop_id>/<general|main|snack|drink>/IMG_1234.jpg
python seed/load_seed.py --inbox
```

Shop IDs: `tesco-tcr`, `sainsburys-warren-st`, `ms-tcr`, `lidl-tcr`, `waitrose-brunswick`, `pret-tcr` (the first run creates the empty folders). Each photo goes through the same pipeline as the app (upright, shrunk, location removed, HEIC ok, duplicates skipped), is read by Claude (4 at a time), and lands in the Review queue as **pending** — nothing is auto-approved. The date used is when the photo was taken. Originals are moved to `seed/inbox_done/`; failed photos stay in the inbox for a re-run. Products with no readable price are listed at the end instead of being queued.

## Publishing to the live site

Review locally, then `python seed/load_seed.py --export` (or **Export approved data** in the Review queue) writes approved real products and deals to `seed/approved.json`. Commit and push it — the deployed app loads it on startup. Shops with approved real data drop their placeholder data; others keep it.

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
# Edit .env with your key, and set ADMIN_PASSCODE to unlock the Review queue

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
admin.py          Team passcode gate for the Review queue
shop_images.py    Shop logos / storefront photos
photo_store.py    uploads/<shop_id>/<general|main|snack|drink>/ photo filing
importer.py       seed/inbox/ drag-and-drop batch import (python seed/load_seed.py --inbox)
nutrition_fill.py Fill missing nutrition by barcode: our data, then Open Food Facts
snapshot.py       Export approved data to seed/approved.json; sync it on startup
openfoodfacts.py  Open Food Facts API client (barcode lookup, per-pack values)
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
- Missing kcal / protein / ingredients are filled by **barcode** only (check digit validated): first from our own photos of the same barcode, then from [Open Food Facts](https://world.openfoodfacts.org) (ODbL). Label values always win, per-pack figures are only used when the pack size is known, and the app shows where each filled value came from. Allergens and diet flags are never filled this way.
- Items with unknown allergen data are excluded when allergen filters are active.
- The Review queue is team-only: unlock it under **Team** in the sidebar with the shared `ADMIN_PASSCODE` (from `.env` locally or Streamlit secrets when deployed). With no passcode set it stays locked. Approve one product, a whole photo, or every clear read at once.
- Re-uploading the same photo is detected by content hash.
- Photos are filed as `uploads/<shop_id>/<general|main|snack|drink>/`, rotated upright, shrunk, and re-saved without EXIF, so location data is never stored. Re-uploading the same photo is detected.
