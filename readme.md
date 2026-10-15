# Deelicious

A lunch optimiser for UCL Bloomsbury students. Set your preferences, and Deelicious finds the best main + snack + drink combo across nearby shops — comparing meal deals against buying separately.

## How it works

1. **Capture** — Upload a shelf-label photo. Claude Vision extracts the item name, price, diet flags and allergens into structured data.
2. **Search** — The optimiser filters by your diet, allergens, budget, walking distance and freshness, then scores every possible lunch with a weighted formula.
3. **Results** — One featured recommendation, up to 3 alternatives at the same shop, and the best option from 3 other nearby shops.

## Features

- **Sidebar preferences** — Max price, walking limit, hot/cold/any, diet chips (vegetarian, vegan, halal), allergen exclusions, loyalty cards (Clubcard / Nectar), sort by quality / distance / price.
- **Deal vs. separate pricing** — Automatically compares the meal deal bundle price against buying items individually.
- **Map view** — OpenStreetMap with colour-coded shop markers and a walking-radius circle.
- **Credits & rewards** — Earn credits for approved photo submissions; redeem them for sponsor vouchers.
- **Freshness tracking** — Every price carries a `last_seen` date and links back to the source photo. Items older than 14 days are excluded from ranking.

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
