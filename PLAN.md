# Meal Deal Finder: Build Plan

Oct 12, 2026 · @Neeam R · **v2 — three-section results, map view, sidebar-only controls**

## Goal and scope

We're building a lunch finder for the UCL Bloomsbury main campus. A student sets their preferences using sidebar controls (budget, walking limit, diet, allergens, loyalty cards) and the app returns the best lunch within walking distance: the exact items to buy and why. Prices come from crowdsourced shelf-label photos, each dated and traceable to the photo it came from.

**In the MVP**

- Claude vision turns a shelf-label or meal deal sign photo into a structured item or deal record.
- Six chains near campus: Pret, M&S, Waitrose, Sainsbury's, Tesco, Lidl.
- Preferences via sidebar controls: max price slider, walking limit slider, hot/cold/any toggle, diet chips, allergen chips, loyalty card toggle, sort dropdown (Quality · Distance · Price).
- An exact optimiser: the best main + snack + drink per shop, comparing meal deal against buying separately.
- Three-section results: one featured best option, up to 3 alternative baskets at the same shop, up to 3 other shops.
- Map view tab: OpenStreetMap with shop markers coloured by rank and a walking-limit radius circle.
- Each result card shows price, walking minutes, last-seen date and a one-line "why" written by Claude.

**Stretch (only after the 1:30 gate on hackathon day)**

- Free-text preference input ("cheap, warm, vegetarian, no nuts") parsed by Claude into sidebar controls.
- Student ratings of items to feed the quality score.
- Live location instead of the campus default.

**Out of scope:** scraping chain websites (photos only), allergy or medical advice (we show label data, not advice), payments, ordering, full accounts (a name-based sign-in for credits is in scope).

---

## What we know about the data

Only Tesco, Sainsbury's and Waitrose clearly sell a standard main + snack + drink meal deal, so the model treats a deal as an optional bundle price over individually priced items. Prices below are as reported on 2026-10-12 and must be re-checked on the shelf.

| Chain | Meal deal found | Price | Source |
| --- | --- | --- | --- |
| Tesco | Yes | £4.25, or £3.85 with Clubcard. Premium £6, or £5.50 with loyalty card | [Grocery Gazette](https://www.grocerygazette.co.uk/2026/10/06/tesco-launches-festive-meal-deal-range/), [Retail Gazette](https://www.retailgazette.co.uk/?p=191928) |
| Sainsbury's | Yes | £3.95. Premium £5 or £5.50 (sources differ; check the shelf) | [Food Manufacture](https://www.foodmanufacture.co.uk/Article/2025/06/23/sainsburys-raises-meal-deal-price/), [Student Beans](https://www.studentbeans.com/blog/uk/best-supermarket-meal-deals-in-the-uk) |
| Waitrose | Yes | £5.50 | [Grocery Gazette](https://www.grocerygazette.co.uk/2026/06/15/waitrose-meal-deal-price/) |
| M&S | No lunch deal found | Only evening Dine In offers found | Confirm on the seed walk |
| Lidl | No lunch deal found | A Lidl director has said it doesn't rely on meal deals | [Woman&Home](https://womanandhome.com/life/news-entertainment/lidl-meal-deal-marks-and-spencer-305353) |
| Pret | Unclear | A meal deal trial was announced; price and rollout unconfirmed | [Marketing Week](https://www.marketingweek.com/pret-meal-deal-value/) |

**Shops near the campus.** Addresses are leads to confirm on the seed walk, not facts to build on.

| Shop | Where we think it is | Status |
| --- | --- | --- |
| Tesco Express | 124-125 Tottenham Court Road | From a 2020 [UCL student blog](https://www.ucl.ac.uk/study/news/2020/dec/best-places-near-ucl-do-your-food-shop); confirm |
| Lidl | 145 Tottenham Court Road | Same blog; confirm |
| M&S Food | 15-17 Tottenham Court Road (opened 9 June 2026), plus a small outlet inside UCLH | [Fitzrovia News](https://fitzrovianews.com/2026/01/09/ms-food-to-move-to-larger-tottenham-court-road-store/) |
| Sainsbury's | Moved to smaller premises on Tottenham Court Road at the end of 2025; address not found | Confirm |
| Waitrose | Possibly The Brunswick Centre (23-39) and a Little Waitrose on Tottenham Court Road | Undated; confirm |
| Pret | Not checked | Confirm |

---

## Team and roles

Three people, three owners, one frozen schema. Swap names in once assigned.

| Person | Role | Owns | Done when |
| --- | --- | --- | --- |
| Intermediate Python #1 | Extraction | `extract.py`: label or deal-sign photo to validated item or deal JSON, plus the review queue data | Every seed-walk photo extracts with price, diet flags and allergens matching the label, or is flagged `needs_review` |
| Intermediate Python #2 | Optimiser | Hard filters, scoring, per-shop search, three-section results output, "why" line generation | Unit tests pass on 3 invented shops; three-section output returns correct primary + alternatives |
| Beginner | UI, seed data, demo | Streamlit app, sidebar controls, three-section results display, map view, seed walk coordination, demo script | A stranger can run the full flow from the UI without help |

All three use Claude (or Claude Code) to write most of the code. Whoever owns a file reviews every change to it.

---

## Tech stack and repo layout

Python for all the logic, SQL for the SQLite store, Streamlit for the UI.

| Element | Language and tools |
| --- | --- |
| Photo extraction | Python, `anthropic` SDK (`claude-opus-4-6`), output validated with Pydantic |
| "Why" line | Python, Claude API returning plain text, using only result fields |
| Storage | SQLite via Python's built-in `sqlite3`; queries are plain SQL |
| Optimiser | Plain Python, tested with `pytest` |
| Credit ledger and earning rules | Python plus a SQLite table |
| Duplicate-photo check, location metadata removal | Python with Pillow and `imagehash` |
| UI | Streamlit (Python, runs as a local web app) |
| Map | `streamlit-folium` + `folium` (Leaflet/OpenStreetMap, no API key) |
| Secrets | `.env` read with `python-dotenv`; `.env` in `.gitignore` |
| Seed shops and walking minutes | Hardcoded in `db.py`; confirmed and updated after the seed walk |

```text
meal-deal-finder/
  app.py            Streamlit UI (beginner)
  extract.py        photo to item or deal JSON, review queue (#1)
  optimiser.py      filters, scoring, per-shop search, three-section output (#2)
  map_view.py       Folium map helper (beginner)
  ledger.py         credit ledger, earning rules, rewards (#2)
  approval.py       pending/approved/rejected flow, pays credits on approval (#2)
  models.py         Pydantic schema, shared and frozen
  db.py             SQLite schema, indexes, one shared connection, seed shops
  seed/             walk photos
  tests/            pytest
  .env              API key, never committed
  requirements.txt
```

Speed: load the database once (`st.cache_resource`), cache search results (`st.cache_data`), call Claude only on button press or file upload — never on a re-render.

---

## Results output structure

The optimiser returns results in three sections. This is the shape the UI and the optimiser must agree on:

**Section A — Primary recommendation (1 result)**
The single top-scoring lunch across all shops. Displayed as a featured card with a primary-colour border.

**Section B — Alternatives at the same shop (up to 3)**
The next 2–3 best baskets at the top-ranked shop, varying the main item (different mains paired with the same best snack and drink). Displayed as secondary cards below the featured card.

**Section C — Other shops (up to 3)**
The best lunch from the 2nd, 3rd and 4th ranked shops. Displayed as secondary cards under a divider.

**Stale (not ranked)**
Items last seen more than 14 days ago are excluded from ranking but shown greyed at the bottom.

The optimiser function signature:

```python
def get_results(
    shops, items, deals, prefs
) -> tuple[Lunch | None, list[Lunch], list[Lunch]]:
    """
    Returns:
      primary       — single best Lunch, or None if no results
      alternatives  — up to 3 more Lunches at primary.shop (vary main)
      other_shops   — best Lunch from the next 3 ranked shops
    """
```

---

## Data schema

Four record types, frozen at kickoff. A change needs all three of us to agree.

```json
// shop  (lat/lng added for map view)
{
  "shop_id": "tesco-tcr",
  "chain": "tesco | sainsburys | waitrose | marks-and-spencer | lidl | pret",
  "name": "string",
  "address": "string",
  "walking_minutes": "number, measured by hand from the agreed campus origin",
  "last_verified": "date",
  "lat": "number (WGS84)",
  "lng": "number (WGS84)"
}

// deal (a bundle price over items)
{
  "deal_id": "string",
  "shop_id": "string",
  "name": "Meal Deal | Premium Meal Deal",
  "price_gbp": "number",
  "loyalty_price_gbp": "number or null",
  "loyalty_scheme": "Clubcard | Nectar | other | null",
  "source_image": "filename",
  "last_seen": "date",
  "submitted_by": "user_id, or null for seed photos",
  "status": "pending | approved | rejected"
}

// item
{
  "item_id": "string",
  "shop_id": "string",
  "name": "string",
  "category": "main | snack | drink",
  "price_gbp": "number",
  "loyalty_price_gbp": "number or null",
  "meal_deal_eligible": "true | false | null",
  "temperature": "hot | cold | ambient",
  "diet_flags": ["vegetarian", "vegan", "...only if printed on the label"],
  "allergens": ["...only as printed on the label"],
  "ingredients_text": "string or null",
  "premium_range": "true | false | null",
  "quality_rating": "1 to 5 from student ratings, or null",
  "source_image": "filename",
  "source_text": "label wording the price, diet flags and allergens were read from",
  "last_seen": "date",
  "submitted_via": "seed | upload",
  "submitted_by": "user_id, or null for seed photos",
  "status": "pending | approved | rejected",
  "confidence": "high | medium | low",
  "needs_review": "true if any field was ambiguous"
}

// user (minimal)
{
  "user_id": "string",
  "handle": "string",
  "reputation": "number"
}
```

- Diet flags and allergens come only from printed label text. Anything unreadable is `null`, never inferred.
- An item with `null` allergen data is excluded from any search where the user lists an allergen.
- `temperature` is `hot` only if the item was seen sold hot.
- `quality_rating` comes from students, never from Claude.
- Every price carries `last_seen` and the photo it came from.

---

## Preferences (sidebar controls → Preferences model)

The UI collects preferences through sidebar controls. These map to the `Preferences` model:

| Sidebar control | Field | Default |
|----------------|-------|---------|
| Max price slider (£2–£14) | `max_price_gbp` | None (no cap) |
| Walking limit slider (2–30 min) | `max_walking_minutes` | 10 |
| Hot / Cold / Any segmented control | `temperature_pref` | "any" |
| Diet chips (Vegetarian, Vegan, Halal) | `diet_flags` | [] |
| Allergen chips (Gluten, Milk, Egg, Nuts, Sesame, Soy, Fish, Shellfish) | `allergens_exclude` | [] |
| Loyalty toggle (Clubcard + Nectar) | `has_clubcard`, `has_nectar` | False |
| Sort dropdown (Quality / Distance / Price) | `sort` | "quality" |

**Sort → score weight mapping:**

| Sort option | Effect |
|------------|--------|
| Quality | `quality_weight=5`, others=1 |
| Distance | rank by `walking_minutes` ascending after score |
| Price | `price_weight=5`, others=1 |

---

## Optimiser and ranking logic

Hard filters remove anything unsafe or out of range. A weighted score ranks the rest. Because the score is additive, the best lunch per shop is found exactly without searching combinations.

**Hard filters (all must pass)**

- Status is approved (or pending when the user has no diet or allergen need).
- Carries every diet flag the user requires.
- Lists none of the allergens the user excludes. Items with `null` allergen data are excluded when any allergen is set.
- `last_seen` is within 14 days.
- The shop is within the walking limit.
- Total price is within the user's cap, if set.
- If hot/cold/any is set to "hot" or "cold", the main must match.

**Score formula**

```
U = w_p * (1 - P / P_max) + w_q * Q + w_h * H
```

- P = lunch price (deal or sum of items, using loyalty prices if applicable). Clamped at 0.
- P_max = user's price cap or £10 default ceiling.
- Q = mean quality score: (q−1)/4 per item; unrated = 0.5; premium range +0.1 (capped at 1).
- H = 1 if main is hot, else 0.
- Weights from sort selection (see table above), normalised to sum to 1.

**Exact search per shop**

1. **Separate mode:** pick best main, snack, drink independently by score contribution.
2. **Deal mode:** use only `meal_deal_eligible` items at the fixed deal price; pick by quality and warmth.
3. Return the higher-scoring mode. Rank shops by U, break ties by walking minutes.

**Three-section output**

After ranking:
1. `primary` = top-ranked shop's best lunch.
2. `alternatives` = up to 3 more baskets at `primary.shop`, varying the main (2nd, 3rd, 4th best mains, each paired with the same best snack and drink).
3. `other_shops` = best lunch from the 2nd, 3rd and 4th ranked shops.

**Where Claude fits**
- Reads label photos → structured JSON (never decides allergen or diet status).
- Writes the one-line "why" using only fields from the result.
- Free-text preference parsing is a stretch feature only (not in the primary UI).

---

## Credits and sponsor rewards

Students earn credits for approved photos and spend them on sponsor rewards.

**Earning rules**

- Credits awarded only on approval, never on upload.
- Base: 10 credits per approved item photo, 20 for a meal deal sign.
- Freshness bonus: 2× credits if the previous record for that item is older than 14 days.
- Coverage bonus: +10 for the first photo of a shop/category with no current data.
- Confirmation: +5 credits if a new photo confirms an existing price.
- Cap: 100 credits per user per day.
- Correction reverses credits if a record is later proven wrong.

**Keeping data honest**

- Reject duplicate photos by image hash.
- Claude must find a readable price label or no credits are paid.
- Items flagged `needs_review` earn nothing until a human approves them.
- Strip EXIF location data from every uploaded photo.
- Reputation multiplier 1.0–1.5 for consistently good submitters.

**Rewards (mocked for hackathon)**

- Sponsors supply voucher codes; we never handle cash.
- For the hackathon, use placeholder sponsors and say so in the demo.
- Redemption spends credits for a single-use code from a sponsor pool.
- Sponsors never influence ranking.

---

## Before the hackathon

**Everyone**
- [x] Freeze the schema.
- [x] Shared repo, API key in `.env`, `.env` in `.gitignore`.
- [ ] Agree campus origin point (Main Quad, Gower Street suggested). Measure walking minutes to each shop by hand. Record the date.
- [ ] Seed walk: ~15 shelf labels per shop (mains, snacks, drinks), meal deal sign, any hot item. Note shop, address, date. Keep photos in `/seed`.

**Intermediate #1: extraction**
- [x] `extract.py`: photo + shop + date → item JSON, validated with Pydantic, one retry on parse failure.
- [x] Deal-sign mode: photo → deal JSON.
- [ ] Run every walk photo through it; compare fields with label by eye; tighten the prompt.
- [x] Diet flags and allergens only from visible label text; `null` otherwise.

**Intermediate #2: optimiser**
- [x] Hard filters, score and per-shop search, with unit tests on 3 invented shops.
- [x] Tests: one shop where deal wins, one where separate wins, one allergen exclusion.
- [ ] `get_results()` returning (primary, alternatives, other_shops) tuple.
- [ ] "Why" prompt that may only use fields from the result.

**Beginner: UI, seed data, demo**
- [ ] Streamlit sidebar: allergen chips, diet chips, sliders, hot/cold/any, loyalty toggle, sort dropdown.
- [ ] Three-section results layout: Section A featured card, Section B alternatives, Section C other shops.
- [ ] Map view tab using `streamlit-folium`.
- [ ] Shop table with name, address, walking minutes and coordinates.
- [ ] First draft of demo script.

---

## Hackathon day

Four-hour slot. The 1:30 gate matters more than the exact timings.

1. **0:00–0:20, integrate.** Load seed data into SQLite. Run optimiser from CLI to confirm results.
2. **0:20–1:30, build end to end.** #1 finishes batch extraction and review screen. #2 wires `get_results()` to UI. Beginner builds three-section cards and map tab.
3. **1:30, gate.** Set sidebar preferences → three-section results with correct seed prices. Ugly is fine; if not passing, drop all stretch items and fix.
4. **1:30–2:45, polish.** Add "why" lines, map view, stale-items greyed section, empty/no-results states, credit ledger, mocked rewards page.
5. **2:45–3:30, rehearse.** Demo twice with a timer. Check five prices against their photos.
6. **3:30–4:00, buffer.** Nothing new is built.

---

## Demo script

About 3–4 minutes. Rehearse twice with a timer.

1. **Problem (20 s).** Lunch deals differ by shop, loyalty card and diet. Nobody compares them.
2. **Capture (30 s).** Upload a shelf-label photo. Show the extracted record beside the photo, with its date, and the credits it will earn once approved.
3. **Preferences (30 s).** Set the sidebar: walk limit 5 min, vegetarian, no nuts. Show how the results change instantly.
4. **Results (60 s).** Show the three-section layout: featured best option at the top, two alternatives at the same shop, three other nearby shops. Point out the "why" line and the freshness date. Show one item excluded because its allergen data was missing.
5. **Deal or separate (30 s).** Show a shop where the meal deal wins and one where buying separately wins.
6. **Map (20 s).** Switch to the map tab — same results, pins coloured by rank, walking-limit circle.
7. **Close (20 s).** What Claude does (reads labels, explains), the exact optimiser (not a heuristic), what's next (more shops, real sponsors).

**Backup:** keep the seed database and cached "why" lines so the demo runs without the API. Record a capture before the event.

---

## Risks, fallbacks and compliance

| Risk | Fallback |
| --- | --- |
| Stale or wrong prices | `last_seen` on every price, old prices filtered out, source photo shown. |
| Wrong allergen or diet data | Flags only from printed label text; `null` means excluded; permanent "check the label" notice. |
| Too few submissions by demo day | Seed walk covers ~15 items per shop. Nothing depends on live uploads. |
| Claude misreads a label | `needs_review` flag; side-by-side review screen; every walk photo compared by eye. |
| M&S, Lidl or Pret have no meal deal | Separate mode prices them item by item; they still rank. |
| Hot food not always available | `hot` only if seen sold hot; result shows when last seen. |
| API outage or venue Wi-Fi | Local database, cached "why" lines, recorded capture. |
| Junk uploads | Everything lands in the review queue; a photo is required. |
| Scope creep | Stretch list stays frozen until the 1:30 gate passes. |

**Compliance.** The MVP uses in-store photos only, no scraping. Keep faces out of photos.

---

## Sources

Price and store facts as reported on 2026-10-12. Re-check every figure on the shelf.

- [Grocery Gazette: Tesco festive meal deal range](https://www.grocerygazette.co.uk/2026/10/06/tesco-launches-festive-meal-deal-range/)
- [Retail Gazette: Tesco meal deal price rise](https://www.retailgazette.co.uk/?p=191928)
- [Food Manufacture: Sainsbury's raises meal deal price](https://www.foodmanufacture.co.uk/Article/2025/06/23/sainsburys-raises-meal-deal-price/)
- [Student Beans: supermarket meal deals 2026](https://www.studentbeans.com/blog/uk/best-supermarket-meal-deals-in-the-uk)
- [Grocery Gazette: Waitrose meal deal price](https://www.grocerygazette.co.uk/2026/06/15/waitrose-meal-deal-price/)
- [Marketing Week: Pret meal deals](https://www.marketingweek.com/pret-meal-deal-value/)
- [Woman&Home: Lidl and meal deals](https://womanandhome.com/life/news-entertainment/lidl-meal-deal-marks-and-spencer-305353)
- [UCL: food shops near campus (2020)](https://www.ucl.ac.uk/study/news/2020/dec/best-places-near-ucl-do-your-food-shop)
- [Fitzrovia News: M&S move to 15-17 Tottenham Court Road](https://fitzrovianews.com/2026/01/09/ms-food-to-move-to-larger-tottenham-court-road-store/)
- [Fitzrovia News: new M&S opens](https://fitzrovianews.com/2026/06/09/ms-food-opens-a-larger-store-on-tottenham-court-road/)
- [RAI: Bloomsbury food options](https://therai.org.uk/conferences/anthropology-and-photography/food-and-drink)
