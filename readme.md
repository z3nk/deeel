# Deeelicious 🥪🥤

A lunch optimiser built for **UCL Bloomsbury** students. Set your budget, diet, and walking limit, and Deeelicious finds the best main + snack + drink combination across nearby shops — automatically comparing meal deal bundle prices against buying items separately.

👉 **Try the live app:** [https://deeelicious.streamlit.app/](https://deeelicious.streamlit.app/)

---

## What It Does

Grabbing lunch around campus shouldn't be a gamble of walking around hungry, guessing which meal deal saves you money, or worrying about allergens.

Deeelicious scans real shelf prices and nutrition data from shops near UCL to give you:
- **The Best Deal First** — One top-rated lunch combination tailored to your exact diet and budget.
- **Shop Alternatives** — Want a different main or drink? See the best swaps at the same shop without leaving.
- **Nearby Shop Comparisons** — See what other supermarkets just a few minutes away offer for the same price.
- **Deal vs. Separate Pricing** — Automatic maths showing exactly how much you save with a meal deal versus purchasing items individually.
- **Interactive Map** — Visualise walking distances from UCL campus with colour-coded shop pins and walking radius boundaries.

---

## Supported Shops (Near UCL Bloomsbury)

All within easy walking distance of the main UCL campus:
- **Tesco Express** · Tottenham Court Road
- **Sainsbury's Local** · Warren Street (21 Hampstead Road)
- **M&S Food** · Tottenham Court Road
- **Lidl** · Tottenham Court Road
- **Waitrose** · Brunswick Centre
- **Pret A Manger** · Tottenham Court Road

---

## How It Works

1. **Set Your Preferences**
   - **Budget & Distance**: Slide your maximum spend and walking time (e.g. within an 8-minute walk).
   - **Dietary Choices**: Pick dietary chips including **Vegetarian**, **Vegan**, **Halal**, and **Kosher**.
   - **Allergen Protection**: Exclude items containing gluten, dairy, nuts, soy, egg, and other major allergens.
   - **Nutrition Targets**: Set minimum protein thresholds and maximum calorie caps for the whole meal.
   - **Preferences**: Choose hot, cold, or any food; toggle Clubcard and Nectar loyalty card pricing.
   - **Sorting**: Rank by **Deeel score**, overall quality, walking distance, or lowest price.

2. **Explore Your Recommendations**
   - **Top Pick (Section A)**: The single best main, snack, and drink combination for your preferences.
   - **Same-Shop Swaps (Section B)**: Alternative combinations at that shop if you fancy something else.
   - **Other Shops (Section C)**: The best options from other nearby shops.

3. **Earn Credits & Help Other Students**
   - Snap photos of supermarket shelves and meal deal labels on your phone.
   - Upload them to keep prices and stock up-to-date.
   - Earn credits when your photo is approved, redeemable for rewards and vouchers.

4. **Interactive Tour**
   - Click the **?** button in the top right of the app anytime for an interactive tour through all features with live data.

---

## The Deeel Score (0–100)

Every lunch combo receives an objective **Deeel score** out of 100 based entirely on verified printed label data:

| Factor | Weight | Scoring Criteria |
|---|:---:|---|
| **Value** | **30 pts** | Price scaled from £3.00 (maximum points) to £8.00 (zero points) |
| **Fillingness** | **25 pts** | Whole-meal protein (30 g for full marks) and energy (650 kcal for full marks) |
| **Ingredient Quality** | **25 pts** | Based on NOVA food processing principles — whole ingredients score higher than ultra-processed additives (mains weighted 2×) |
| **Nutrition Balance** | **10 pts** | Proportion of total meal calories derived from protein (25% for full marks) |
| **Deal Saving** | **10 pts** | Percentage saved by buying as a meal deal compared to buying items separately (35% saving for full marks) |

### Ingredient Quality Breakdown
- **Processing Markers**: Penalises industrial additives typical of ultra-processed food (artificial colours, chemical preservatives, emulsifiers/thickeners, flavour enhancers, artificial sweeteners, modified starches, flavourings, glucose syrups, and hydrogenated fats).
- **Safe Additives Ignored**: Harmless antioxidants, vitamin C, citric acid, and natural leavening agents are not penalised.
- **Short Ingredients Lists**: Whole-food recipes with fewer ingredients score higher.
- Tap the **"How it's scored"** button on any recommendation card to see a transparent breakdown of points and ingredient notes.

---

## Food Safety & Trust

- **Label First**: Diet flags come strictly from printed packaging labels. Allergens are read from labels too; where a photo didn't show them, they're filled by barcode from another photo of the same product or from [Open Food Facts](https://world.openfoodfacts.org) — and the app always says where they came from.
- **Check the Pack**: All allergen information is read by computer and may be wrong or incomplete. The app shows this warning next to every allergen it displays — always check the packaging yourself.
- **Safety First**: If allergen information for an item is missing or unverified, that item is automatically excluded when that allergen filter is enabled. Allergens from Open Food Facts can exclude an item but never clear one — only allergens read from a printed label can.
- **Freshness Window**: Prices and items carry a `last_seen` timestamp. Any product older than 14 days is automatically retired from active rankings.
- **Privacy Protected**: Uploaded photos are stripped of all EXIF and GPS location metadata before being processed.

---

## Developer & Technical Information

Looking to run the app locally, run tests, or contribute to development?

See the [Developer Guide (dev.md)](dev.md) for:
- Local setup and environment configuration
- Tech stack overview (Streamlit, SQLite, Claude Vision, Folium)
- Publishing data to live site (`seed/approved.json`)
- Batch photo import pipeline (`seed/inbox/`)
- Test suite execution (`pytest`)
- Project architecture and data schemas
