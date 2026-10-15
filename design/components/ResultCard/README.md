The card that shows one shop's best main + snack + drink basket, its price, deal status and Deeel score.

Used in all three result sections. Hand-written from `app.py` (`render_result_card`) and DESIGN_BRIEF.md §6.

## Variants
- **Featured** (`dl-card dl-card--featured`): Section A, "Your best option". `border-width-strong` in `primary` on `primary-tint`, with the "Best match" badge. On the tint, all secondary text uses `text`, never `text-muted`.
- **Secondary** (`dl-card`): Sections B ("More at {shop}", omit the rank) and C ("Other nearby shops"). Hairline `border`, `surface`. Price may drop to 20px.
- **Stale** (`dl-card dl-card--stale`): below all sections, not ranked. `sample-tint`, "Data too old" badge, "Not ranked — last seen over 14 days ago" in `stale`. Do not dim with opacity (the code's `opacity:0.4` fails contrast).

## The consumer provides
Rank (1–3), shop (chain key + name), walk minutes, the basket line, nutrition (kcal, protein, "partly from Open Food Facts" if filled), allergens, price, separate price or null, deal state, Deeel score, freshness in days, sample-data flag.

## Rules
- Order: rank · shop badge + name · badges · walk → basket → nutrition → allergen line with the short warning → price row → score, freshness, "See basket →".
- Always state the deal: the savings sticker ("Meal deal saves £1.70"), "Bought separately — no deal", or "some items are only priced as part of the deal".
- The allergen line always carries `⚠️ computer-read — check the pack` (see AllergyWarning).
- The savings sticker is the only hype element on the card. Never put sticker styling on allergen, sample-data or price-guarantee text.

## Streamlit
`st.container(border=True)` holding one `st.markdown(..., unsafe_allow_html=True)` block with these classes; the featured border comes from the injected CSS. "See basket →" is an `st.button`. The "How it's scored" popover is `st.popover`.
