# Handover Document: `Zen-push-1`

- **Branch**: [`Zen-push-1`](https://github.com/z3nk/deeelicious/tree/Zen-push-1)
- **Author**: Zen
- **Test Suite Status**: All 92 tests passing (`pytest`)
- **Base Parent**: Commit `8dd5d13` (unmerged from upstream `origin/main` commits)

---

## 1. Summary of Changes & Features

### A. Official Supermarket Vector Logos
* **Files Added**:
  - `assets/logos/tesco.svg` (Tesco official wordmark)
  - `assets/logos/sainsburys.svg` (Sainsbury's official wordmark)
  - `assets/logos/lidl.svg` (Lidl official roundel)
  - `assets/logos/waitrose.svg` (Waitrose & Partners wordmark)
  - `assets/logos/marks-and-spencer.svg` (M&S logo)
  - `assets/logos/pret.svg` (Pret A Manger star logo)
* **Code Integration**:
  - `shop_images.py`: Extended `logo_html()` to check for vector SVG files first (`.svg`), encoding them as base64 data URIs (`image/svg+xml`) with clean rendering before falling back to `.png` or text-letter badges.

---

### B. Map View: Basket Navigation Fix & Brand Pin Styling
* **Files Modified**: `map_view.py`, `app.py`
* **Fix for "See basket" Navigation**:
  - Previously, clicking "See basket" inside a Folium map popup could not communicate with Streamlit due to isolated iframe scoping.
  - Added interactive selection sync: When a marker is clicked on the map, a **Selected Shop Card** renders directly below the map showing the supermarket logo, address, walk time, meal price, and meal deal badges.
  - Placed a native Streamlit button: `st.button("See basket →", key=f"map_see_basket_{active_id}")` which directly sets `st.session_state.active_shop_id = active_id` and triggers an immediate view transition into the shop's lunch basket.
* **Brand Colour-Coded Map Markers**:
  - Replaced generic red map pins with custom SVG markers matching brand identity:
    - **Tesco**: `#00539F` (Tesco Blue)
    - **Sainsbury's**: `#E05A00` (Sainsbury's Orange)
    - **Waitrose**: `#005522` (Waitrose Dark Green)
    - **Lidl**: `#002C6C` (Lidl Navy)
    - **M&S**: `#1B4332` (M&S Deep Green)
    - **Pret**: `#8B1D2C` (Pret Burgundy)
  - Markers display clear numeric rankings (e.g. `1`, `2`, `3`) inside the pin head.

---

### C. Deal Score Breakdown Popover & Sub-Bar Colour Coding
* **Files Modified**: `app.py`, `demo.py`
* **Popover Container**:
  - Replaced bulky inline progress bars with a compact popover dropdown (`st.popover(f"Score: {int(deeel.total)}/100")`).
* **Cleaned Raw Values**:
  - Removed raw mathematical component numbers (e.g., raw weights and formula numbers) that were cluttering the UI.
  - Retained clean labels and normalized component bars.
* **Component-Specific Progress Bar Colours**:
  - Updated progress bars to match their own individual sub-scores rather than all displaying green:
    - Sub-score $\ge 70\%$: Green (`#16a34a`)
    - Sub-score between $40\%$ and $69\%$: Amber / Orange (`#f59e0b`)
    - Sub-score $< 40\%$: Red (`#ef4444`)

---

### D. Header URL Anchor Links Removed
* **Files Modified**: `app.py`
* Injected CSS to hide the hover hyperlink copy button that Streamlit attaches to header elements (`h1`, `h2`, `h3`):
  ```css
  .stHeadingWithActionElements button,
  [data-testid="stHeaderActionElements"] {
      display: none !important;
  }
  ```

---

### E. Sidebar Filters Redesign
* **Files Modified**: `app.py`, `models.py`
* **Compact Allergen Multiselect**:
  - Converted allergen checkboxes into an expandable `st.multiselect("Allergens — avoid", ...)` dropdown to save sidebar height.
  - Removed the grey disclaimer text (`"items with unchecked allergen labels are hidden..."`) as requested.
* **3-State Hot / Cold Segmented Selector**:
  - Converted the temperature selector to a 3-stage segmented button layout (`All`, `Hot`, `Cold`) using `st.segmented_control` (with fallback to horizontal `st.radio`). Selecting one option automatically deselects the others.
* **Loyalty Cards Default**:
  - Updated `models.Preferences` so all loyalty cards (`has_clubcard`, `has_nectar`, `has_lidl_plus`, `has_sparks`, `has_mywaitrose`, `has_club_pret`) default to `True`.

---

### F. Loyalty Card Pricing Engine Expansion & Tests
* **Files Modified**: `optimiser.py`, `tests/test_optimiser.py`
* Updated `_item_qualifies_for_loyalty()` and `_deal_qualifies_for_loyalty()` to recognize Lidl Plus, Sparks, myWaitrose, and Club Pret.
* Added `TestLoyaltyCards` in `tests/test_optimiser.py` covering card price application and isolation across schemes.

---

## 2. File Diff Summary

| File | Changes Made |
|---|---|
| `assets/logos/*.svg` | 6 new official supermarket vector logos (Tesco, Sainsbury's, Lidl, Waitrose, M&S, Pret) |
| `shop_images.py` | SVG logo loader with base64 data URI |
| `map_view.py` | Brand color map markers + rankings, selected shop preview card integration |
| `app.py` | Hide header URL links, compact allergy multiselect, 3-state segmented hot/cold selector, deal score popover with dynamic sub-bar colors, map basket button listener |
| `models.py` | Loyalty card preferences default to `True` |
| `optimiser.py` | All loyalty cards discount checks in single-item and meal-deal scoring |
| `demo.py` | Deal score popover matching app.py |
| `tests/test_optimiser.py` | Unit tests for loyalty card pricing |
| `readme.md` | Documentation update |

---

## 3. Verification

```bash
pytest
# Output: 92 passed, 1 warning in 9.00s
```
