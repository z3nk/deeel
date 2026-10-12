# Meal Deal Finder: Build Plan

Oct 12, 2026 · @Neeam R

## Goal and scope

We're building a lunch finder for the UCL Bloomsbury main campus. A student says what matters (price, ingredient quality, a warm lunch) and their dietary needs, and the app returns the best lunch within walking distance: the exact items to buy and why. Prices come from crowdsourced shelf-label photos, each dated and traceable to the photo it came from.

**In the MVP**

- Claude vision turns a shelf-label or meal deal sign photo into a structured item or deal record.
- Six chains near campus: Pret, M&S, Waitrose, Sainsbury's, Tesco, Lidl.
- Preferences as free text ("cheap, warm, vegetarian, no nuts") or sliders, plus a loyalty-card toggle.
- An exact optimiser: the best main + snack + drink per shop, comparing the meal deal against buying items separately.
- Ranked results with price, walking minutes from campus, last-seen date and a one-line "why".

**Stretch (only after the gate in Hackathon day)**

- Student ratings of items to feed the quality score.
- Live location instead of the campus default.

**Out of scope:** scraping chain websites (photos first), allergy or medical advice (we show label data, not advice), payments, ordering and full accounts (a light sign-in to hold credits is in scope).

## What we know about the data

Only Tesco, Sainsbury's and Waitrose clearly sell a standard main + snack + drink meal deal, so the model treats a deal as an optional bundle price over individually priced items. Prices below are as reported on 2026-10-12 and must be re-checked on the shelf.

| Chain | Meal deal found | Price | Source |
| --- | --- | --- | --- |
| Tesco | Yes | £4.25, or £3.85 with Clubcard. Premium £6, or £5.50 with a loyalty card | [Grocery Gazette](https://www.grocerygazette.co.uk/2026/10/06/tesco-launches-festive-meal-deal-range/), [Retail Gazette](https://www.retailgazette.co.uk/?p=191928) |
| Sainsbury's | Yes | £3.95. Premium £5 or £5.50 (sources differ; check the shelf) | [Food Manufacture](https://www.foodmanufacture.co.uk/Article/2025/06/23/sainsburys-raises-meal-deal-price/), [Student Beans](https://www.studentbeans.com/blog/uk/best-supermarket-meal-deals-in-the-uk) |
| Waitrose | Yes | £5.50 | [Grocery Gazette](https://www.grocerygazette.co.uk/2026/06/15/waitrose-meal-deal-price/) |
| M&S | No lunch deal found | Only evening Dine In offers found | Confirm on the seed walk |
| Lidl | No lunch deal found | A Lidl director has said it doesn't rely on meal deals (undated article) | [Woman&Home](https://womanandhome.com/life/news-entertainment/lidl-meal-deal-marks-and-spencer-305353) |
| Pret | Unclear | A meal deal trial was announced; price and rollout unconfirmed | [Marketing Week](https://www.marketingweek.com/pret-meal-deal-value/) |

**Shops near the campus.** Addresses are leads to confirm on the seed walk, not facts to build on.

| Shop | Where we think it is | Status |
| --- | --- | --- |
| Tesco Express | 124-125 Tottenham Court Road | From a 2020 [UCL student blog](https://www.ucl.ac.uk/study/news/2020/dec/best-places-near-ucl-do-your-food-shop); confirm |
| Lidl | 145 Tottenham Court Road | Same blog; confirm |
| M&S Food | 15-17 Tottenham Court Road (opened 9 June 2026), plus a small outlet inside UCLH | [Fitzrovia News](https://fitzrovianews.com/2026/01/09/ms-food-to-move-to-larger-tottenham-court-road-store/) |
| Sainsbury's | Moved to smaller premises on Tottenham Court Road at the end of 2025; address not found | Confirm |
| Waitrose | Possibly The Brunswick Centre (23-39) and a Little Waitrose on Tottenham Court Road | Undated [pages](https://therai.org.uk/conferences/anthropology-and-photography/food-and-drink); confirm |
| Pret | Not checked | Confirm |

## Team and roles

Three people, three owners, one frozen schema. Swap names in once assigned.

| Person | Role | Owns | Done when |
| --- | --- | --- | --- |
| Intermediate Python #1 | Extraction | `extract_item.py`: label or deal-sign photo to validated item or deal JSON, plus the review queue data | Every seed-walk photo extracts with price, diet flags and allergens matching the label, or is flagged `needs_review` |
| Intermediate Python #2 | Optimiser | Hard filters, scoring, per-shop search, and the prompt that turns free text into filters and sliders | Unit tests pass on 3 invented shops; 10 free-text phrasings produce the right filters |
| Beginner | UI, seed data, demo | Streamlit app, shop list with walking minutes, seed walk coordination, demo script | A stranger can run the full flow from the UI without help |

All three use Claude (or Claude Code) to write most of the code. Whoever owns a file reviews every change to it, so vibe-coded output still gets read by a human.

## Tech stack and repo layout

Python for all the logic, SQL for the SQLite store, Streamlit for the UI. One language means all three of us can read each other's code.

| Element | Language and tools |
| --- | --- |
| Photo extraction | Python, `anthropic` SDK, output validated with Pydantic |
| Free-text parsing and the "why" line | Python, Claude API returning JSON, validated with Pydantic |
| Storage | SQLite via Python's built-in `sqlite3`; queries are plain SQL |
| Optimiser | Plain Python, tested with `pytest` |
| Credit ledger and earning rules | Python plus a SQLite table |
| Duplicate-photo check, location metadata removal | Python with Pillow and an image-hash library such as `imagehash` |
| UI | Streamlit (Python, runs as a local web app) |
| Secrets | `.env` read with `python-dotenv`; `.env` in `.gitignore` |
| Seed shops and walking minutes | A JSON or CSV file |

```text
meal-deal-finder/
  app.py            Streamlit UI (beginner)
  extract.py        photo to item or deal JSON, review queue (#1)
  optimiser.py      filters, scoring, per-shop search (#2)
  ledger.py         credit ledger, earning rules, rewards (#2)
  approval.py       pending/approved/rejected flow, pays credits on approval (#2)
  models.py         Pydantic schema, shared and frozen
  db.py             SQLite schema, indexes, one shared connection
  seed/             walk photos and seed shops
  tests/            pytest
  .env              API key, never committed
  requirements.txt
```

Speed: Streamlit re-runs the whole script every time someone moves a slider, so the app must do almost nothing on each rerun. Open the database once and reuse it (`st.cache_resource`). Cache search results (`st.cache_data`). Call Claude only when someone presses a button or uploads a photo, never on a rerun. Work out each "why this shop" line when the result is built, not when it is drawn. The optimiser is plain in-memory Python, so a search should take milliseconds. I haven't checked current library versions, so confirm them when you set up the project.

## Architecture

&#91;embedded content: pipeline · 4 stages, 2 ingest paths\]

Photos enter by two routes and Claude turns each into schema-checked JSON. Flagged items wait in the review queue; the rest go to the store. The optimiser combines the store with the student's inputs and the campus walking times, and Claude also writes the one-line reason on each result card.

## Credits and sponsor rewards

Students earn credits for approved photos and spend them on rewards that sponsors supply. Credits are paid for useful, checked data rather than volume, because a price that is wrong or an allergen that is misread is worse than a missing one. All amounts are starting values to tune.

**Earning rules**

- Credits are awarded only when a submission is approved, never on upload. Pending items still appear in the app, labelled unverified, but pay nothing and do not count toward confirmations or reputation.
- Base award: 10 credits per approved item photo, 20 for a meal deal sign.
- Freshness bonus: double credits if the shop's previous record for that item is older than the 14-day limit.
- Coverage bonus: +10 for the first photo of a shop or category that has no current data.
- Confirmation: a new photo that confirms an existing price earns 5 credits and raises that record's confidence.
- Cap of 100 credits per user per day.
- A later correction that proves a record wrong reverses its credits.

**Keeping the data honest**

- Reject duplicate or recycled photos by image hash.
- A Claude vision check must find a readable price label or sign, or no credits are paid.
- Items flagged `needs_review` earn nothing until a human approves them. Spot-check a sample of approved items against a second photo.
- Reputation multiplier from 1.0 to 1.5 for users whose photos are later confirmed; reduced earning for users whose photos are repeatedly rejected.
- Strip location metadata from every uploaded photo.

**Rewards**

- Sponsors supply a reward (a voucher code or a free item); we never handle cash. Examples to pitch: a free coffee, money off a lunch, a society ticket discount. These are placeholders, not agreed partnerships.
- Redemption spends credits for a single-use code from a sponsor-supplied pool, recorded in the ledger.
- Sponsors never influence ranking. Results come only from the optimiser, and any sponsored placement would have to be labelled.
- For the hackathon, build a mocked rewards page with placeholder sponsors and say so in the demo. Real sponsors come after.

**Records**

```json
// credit_event (append-only ledger; balance = sum of credits per user)
{
  "event_id": "string",
  "user_id": "string",
  "type": "earn | spend | reversal",
  "credits": "number (positive earn, negative spend or reversal)",
  "reason": "approved_item | approved_deal | stale_bonus | coverage_bonus | confirmation | reward_redeemed | reversal",
  "ref_id": "item_id or reward_id",
  "created_at": "datetime"
}

// reward
{
  "reward_id": "string",
  "sponsor": "string",
  "title": "string",
  "cost_credits": "number",
  "codes_remaining": "number",
  "expires": "date or null"
}

// user (minimal)
{
  "user_id": "string",
  "handle": "string",
  "reputation": "number"
}
```

No real names or emails in the MVP: sign in with a handle, and show a redeemed code in the app.

**Who builds it.** #2 builds the ledger and earning rules (one SQLite table and a few functions). #1 connects the approval event to the award. The beginner builds the balance display and the mocked rewards page.

**Open points to check before real sponsors.** Whether UCL or the Students' Union has rules on commercial promotion on campus, and whether rewards raise any tax or promotion-rules issue. I haven't checked either, and I'm not a lawyer.

## Data schema

Three record types, frozen at kickoff. A change needs all three of us to agree.

```json
// shop
{
  "shop_id": "tesco-tcr",
  "chain": "tesco | sainsburys | waitrose | marks-and-spencer | lidl | pret",
  "name": "string",
  "address": "string",
  "walking_minutes": "number, measured by hand from the agreed campus origin",
  "last_verified": "date"
}

// deal (a bundle price over items)
{
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
```

- Diet flags and allergens come only from printed label text. Anything unreadable is `null`, never inferred.
- An item with `null` allergen data is excluded from any search where the user lists an allergen.
- `temperature` is `hot` only if the item was seen sold hot.
- `quality_rating` comes from students, never from Claude. `premium_range` is read from the label or range name.
- Every price carries `last_seen` and the photo it came from.

Pending records are shown in the app, labelled unverified; rejected ones never are. A search with a diet or allergen need uses only records with `status: approved` only. Credits are paid to the user in `submitted_by` when a record moves from `pending` to `approved`.

## Optimiser and ranking logic

Hard filters remove anything unsafe or out of range, a weighted score ranks the rest, and because the score is additive the best lunch per shop is found exactly, without searching combinations.

**Hard filters (an item or shop must pass all)**

- Is approved (or pending, when the user has no diet or allergen need) and carries every diet flag the user requires (for example vegetarian).
- Lists none of the allergens the user excludes. Items with `null` allergen data are excluded when any allergen is listed.
- `last_seen` is within 14 days (a starting default, adjustable).
- The shop is within the walking limit (starting default 10 minutes, adjustable).
- Total price is within the user's cap, if they set one.

**Score for a candidate lunch**

```latex
U = w_p \left(1 - \frac{P}{P_{max}}\right) + w_q\, Q + w_h\, H
```

- P = the lunch price: the deal price if bundled, otherwise the sum of the three item prices, using loyalty prices if the user has that card. The price term is clamped at 0.
- P\_max = the user's price cap if set, otherwise a fixed ceiling (start at £10).
- Q = the mean of (q - 1) / 4 over the three items, where q is the student rating. An unrated item counts as 0.5, and a premium-range item adds 0.1 (capped at 1). These are starting values to tune on the seed data.
- H = 1 if the main is hot, otherwise 0.
- The user's three sliders (price, quality, warmth, 0 to 5) are normalised so the weights sum to 1; if all are 0, the weights are equal.

**Exact search per shop**

P is a sum, Q is a mean and H depends only on the main, so U is additive across the three items. For each shop and each pricing mode, the best lunch is the best main, best snack and best drink chosen independently.

1. **Separate mode:** score each remaining item by its contribution to U and take the best in each category.
2. **Deal mode:** use only `meal_deal_eligible` items. The price is fixed at the deal price, so pick by quality and warmth.
3. Keep the higher of the two modes per shop, then rank shops by U, breaking ties by walking minutes.

**Where Claude fits.** Claude turns free text into sliders and filters, reads label photos, and writes the one-line "why" using only fields from the result. Claude never decides allergen or diet status; that comes from label text alone.

## Before the hackathon

Build and test the pieces separately now, so the hackathon itself is integration.

**Everyone**

- [ ] Freeze the schema above.
- [ ] Shared repo, API key in `.env`, `.env` in `.gitignore` (never commit a key).
- [ ] Agree one campus origin point (for example the Main Quad on Gower Street) and measure walking minutes to each shop once, by hand, from a maps app. Record the date.
- [ ] Seed walk, one lunch break, split between us: photograph about 15 shelf labels per shop (mains, snacks, drinks), the meal deal sign, and any hot item. Note shop, address and date. Keep the photos in `/seed`.

**Intermediate #1: extraction**

- [ ] `extract_item.py`: photo + shop + date to item JSON, validated with Pydantic, one retry on a parse failure.
- [ ] Deal-sign mode: photo to deal JSON.
- [ ] Run every walk photo through it, compare each field with the label by eye, log errors and tighten the prompt.
- [ ] Diet flags and allergens only from visible label text; `null` otherwise.

**Intermediate #2: optimiser**

- [ ] Hard filters, score and per-shop search, with unit tests on 3 invented shops, including one where the deal wins and one where buying separately wins.
- [ ] Prompt that turns free text into filters and sliders as JSON; test it on 10 phrasings.
- [ ] "Why" prompt that may only use fields from the result.

**Beginner: UI, data, demo**

- [ ] Streamlit skeleton: text box, sliders, diet checkboxes, loyalty-card toggle, result cards with photo thumbnail and last-seen date, upload box.
- [ ] Shop table with name, address and walking minutes.
- [ ] First draft of the demo script.

## Hackathon day

The plan assumes a 4-hour slot. Scale the timings if yours differs; the gate at 1:30 matters more than the exact minutes.

1. **0:00 to 0:20, integrate.** Load the seed shops and items into SQLite and run the optimiser on them from a terminal.
2. **0:20 to 1:30, build end to end.** #1 finishes batch extraction and the review screen. #2 wires the optimiser and free-text parser to the UI inputs. The beginner builds result cards and the upload box.
3. **1:30, gate.** Type a preference, get a ranked list with correct prices from the seed data, even if ugly. If not, drop every stretch item and fix this first.
4. **1:30 to 2:45, polish and "why".** Add the one-line "why", the deal-versus-separate comparison, and a sensible empty state (nothing matches, so show the closest and say which filter was relaxed). Add the credit ledger and a mocked rewards page.
5. **2:45 to 3:30, rehearse.** Run the demo twice with a timer, record a backup capture, and check five prices shown in the demo against their photos.
6. **3:30 to 4:00, buffer and submit.** Nothing new is built in this window.

## Demo script

About 3 to 4 minutes. Rehearse it twice with a timer.

1. **Problem (20 s).** Lunch deals differ by shop, loyalty card and diet, and nobody compares them.
2. **Capture (30 s).** Upload a shelf-label photo and show the extracted record beside the photo it came from, with its date, then the credits it earns once approved.
3. **Preferences (30 s).** Type "cheap, warm, vegetarian, no nuts" and show the sliders and hard filters Claude produced, which the user can edit.
4. **Results (60 s).** Show ranked shops with the exact lunch, price, walking minutes, last-seen date and the "why" line. Show one item excluded because its allergen data was missing, to make the safety rule visible.
5. **Deal or separate (30 s).** Show a shop where the meal deal wins and one where buying items separately wins.
6. **Close (30 s).** What Claude does (reads labels, parses preferences, explains), the physics edge (an exact additive optimiser, not a heuristic), and what's next (more shops, real sponsors).

**Backup:** keep the seed database and cached "why" lines so the demo runs without the API, plus the recorded capture.

## Risks, fallbacks and compliance

| Risk | Fallback |
| --- | --- |
| Stale or wrong prices | `last_seen` on every price, old prices filtered out, source photo shown beside the result. |
| Wrong allergen or diet data | Flags only from printed label text; `null` means excluded from restricted searches; a permanent "check the label" notice; no medical advice. |
| Too few submissions by demo day | The seed walk covers about 15 items per shop. Nothing depends on live submissions. |
| Claude misreads a label | `needs_review` flag and a side-by-side review screen; every walk photo is compared with its record by eye. |
| M&S, Lidl or Pret have no meal deal | Separate mode prices them item by item, so they still rank. |
| Deal prices differ by shop or card | Deals are stored per shop, with a loyalty-card toggle; verify on the shelf during the walk. |
| Hot food is not always available | `hot` only if seen sold hot; the result shows when it was last seen. |
| API outage or venue Wi-Fi | Local database, cached "why" lines, recorded capture. |
| Junk or spam submissions | Everything lands in the review queue; a photo is required. |
| Scope creep | The stretch list stays frozen until the 1:30 gate passes. |

**Compliance.** The MVP uses photos taken in store by people, not scraping. Scraping chain websites is out of the MVP. If you add it later, that's the team's call; run it once ahead of time at a low request rate, store a dated snapshot, and never scrape live during the demo. Keep people's faces out of photos.

## Sources

Price and store facts, as reported on 2026-10-12. Re-check every figure on the shelf.

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
