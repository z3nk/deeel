A pill showing when an item's price was last seen, banded by age.

Hand-written from `app.py` (`_freshness_badge`).

- Under 7 days: `fresh` on `success-tint`. 7–14 days: `ageing` on `warning-tint`. Over 14 days: `stale` on `sample-tint` with "Data too old" (out of ranking).
- Always shows the day count ("● Seen 3d ago"): the colour is never the only signal.
- The unverified tag (`dl-badge--unverified`, `unverified` on `info-tint`) shares this shape and marks items pending review.

The consumer provides: days since last seen; pending status.
