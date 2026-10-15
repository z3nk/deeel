A side-by-side pair comparing the meal deal price with buying the same items separately.

Hand-written from `app.py` (`screen_detail`).

- Two cards in `st.columns(2)`. The cheaper one gets `border-width-strong` in `primary` and "✓ Best option — saves £x" in `success-ink`. The winner is marked by the border AND the text.
- Deal unavailable (a deal-only or not-in-deal item picked): the deal card reads "Not available" with "An item you picked isn't in the meal deal".
- Prices use the `price` style with tabular numerals.

The consumer provides: deal price or null, separate price or null, reason when unavailable.
