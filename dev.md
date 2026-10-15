# Developer Guide

Developer documentation for building, running, and contributing to **Deeelicious**.

For user-facing documentation and feature overviews, see [README.md](README.md).

---

## Tech Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **UI** | [Streamlit](https://streamlit.io/) | Interactive web interface and state management |
| **Storage** | SQLite | Local database (`meal_deal.db`) with WAL mode |
| **Data Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Strict models for items, shops, deals, and preferences |
| **Vision Extraction** | [Anthropic SDK](https://docs.anthropic.com/) | Claude Vision model (`claude-opus-4-6`) for shelf/label extraction |
| **Nutrition Lookup** | Open Food Facts API | Barcode-based nutrition and ingredient filling |
| **Map** | Folium & streamlit-folium | OpenStreetMap rendering with shop markers and radius circles |
| **Image Processing** | Pillow, Pillow-HEIF, Piexif, imagehash | EXIF stripping, rotation, resizing, HEIC conversion, perceptual hashing |
| **Testing** | pytest | Unit and integration test suite |

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/z3nk/deeelicious.git
cd deeelicious

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 3. Environment Variables (`.env`)
Edit `.env` with the following keys:
- `ANTHROPIC_API_KEY`: Your Anthropic API key (required for photo extraction and AI "why" explanations).
- `ADMIN_PASSCODE`: Team passcode to unlock the Review Queue in the sidebar under **Team** (optional locally, required in production to review/approve submissions).

### 4. Run the Application
```bash
streamlit run app.py
```
The application will be available at `http://localhost:8501`.

---

## Project Structure

```
app.py            Streamlit UI and page routing
extract.py        Claude Vision extraction: photo → structured item/deal JSON
optimiser.py      Meal deal & item combination search, filtering, and scoring
deeel.py          Deeel score algorithm (0–100 scale)
ingredients.py    Ingredient quality scoring (NOVA ultra-processing markers & counts)
demo.py           Live guided tour behind the ? button
admin.py          Team passcode gate for the Review queue
shop_images.py    Shop logos and storefront photos
photo_store.py    Photo storage pipeline (uploads/<shop_id>/<category>/)
importer.py       Batch inbox importer (seed/inbox/ folder processing)
nutrition_fill.py Barcode nutrition filling: local DB first, then Open Food Facts
snapshot.py       Export approved data to seed/approved.json; sync it on startup
openfoodfacts.py  Open Food Facts client (barcode lookup, per-pack normalization)
map_view.py       Folium map helper with distance circles and shop markers
ledger.py         Credit ledger, balance checks, and earning rules
approval.py       Review queue: pending/approved/rejected workflow
models.py         Frozen Pydantic schemas (Item, Shop, Deal, Preferences)
db.py             SQLite schema, connection management, and seed loader
seed/             Seed walk data and inbox folders
tests/            Pytest test suite
```

---

## Publishing to the Live Site

Review submissions locally, then export approved items to `seed/approved.json`:
```bash
python seed/load_seed.py --export
```
(Or click **Export approved data** in the Review queue UI).

This writes approved real products and deals to `seed/approved.json`. When committed and pushed, the deployed app on Streamlit Cloud automatically loads this data on startup. Shops with approved real data drop their placeholder seed data, while shops without approved data retain their placeholders.

---

## Batch Photo Import (Seed Walk)

Instead of uploading individual photos through the UI, photos can be batch-imported by dropping them into the `seed/inbox/` directories:

```
seed/inbox/<shop_id>/<category>/IMG_1234.jpg
```

### Supported Shop IDs:
- `tesco-tcr` (Tesco Express, Tottenham Court Road)
- `sainsburys-warren-st` (Sainsbury's Local, Warren Street)
- `ms-tcr` (M&S Food, Tottenham Court Road)
- `lidl-tcr` (Lidl, Tottenham Court Road)
- `waitrose-brunswick` (Waitrose, Brunswick Centre)
- `pret-tcr` (Pret A Manger, Tottenham Court Road)

### Categories:
- `general`: Storefronts, promotional deal signs, mixed shelves
- `main`: Mains only shelf
- `snack`: Snacks only shelf
- `drink`: Drinks only shelf

### Running the Importer:
```bash
python seed/load_seed.py --inbox
```

Each photo is:
1. Stripped of EXIF and GPS metadata.
2. Rotated upright and resized.
3. De-duplicated via perceptual image hash.
4. Processed by Claude Vision in parallel batches.
5. Added to SQLite as **pending** in the Review queue (never auto-approved).
6. Moved to `seed/inbox_done/` (which is git-ignored for privacy).

---

## Testing

Run tests using pytest:
```bash
pytest
```

To run a specific test module:
```bash
pytest tests/test_deeel.py
pytest tests/test_optimiser.py
pytest tests/test_importer.py
```

---

## Review Queue & Admin Access

- Access the Review Queue via the sidebar under **Team**.
- Enter the `ADMIN_PASSCODE` defined in `.env` or Streamlit secrets.
- Review pending items, edit extracted fields, and approve or reject submissions individually or in bulk.
- Approvals trigger credit payments in the user ledger.

---

## Data Integrity & Pipeline Rules

- **Label truth first**: Dietary flags are extracted strictly from visible label text. Allergens are read from labels; gaps are filled by barcode (same-barcode label data, then Open Food Facts). For allergy filters only printed-label allergens count as known — Open Food Facts allergens can exclude but never clear an item. Every allergen display carries the computer-read warning (`ALLERGY_WARNING` in app.py).
- **Barcode enrichment**: Nutrition (kcal, protein), ingredients and allergens missing from photos are populated by barcode validation (internal DB match first, then Open Food Facts).
- **Stale records**: Prices and items older than 14 days are excluded from recommendation rankings.
- **Security & Privacy**: EXIF and GPS data are stripped from every upload before disk persistence. Duplicate images are rejected by image hash.
