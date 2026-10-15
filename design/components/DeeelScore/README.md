The Deeel score badge: "Deeel" plus the 0–100 score on a banded fill.

Hand-written from `app.py` (`_deeel_colour`).

- Bands: `score-high` for 70+, `score-mid` for 50–69, `score-low` under 50, all with `on-primary` text. These are darker than the code's `#16A34A` / `#D97706` / `#94A3B8`, which failed white-text contrast.
- Always print the number: the colour is never the only signal.
- Spelling: "Deeel score" (three Es, capital D, lowercase "score"); the badge reads "Deeel 79".
- Pair it with the "How it's scored" popover (`st.popover`): five bars, Value 30, Fillingness 25, Ingredient quality 25, Nutrition balance 10, Deal saving 10, plus per-item ingredient reasons.
- In marketing the score numeral may be set in `score-numeral` (display face, tabular numerals).

The consumer provides: the integer score.
