# Project: Deeelicious Map View Modernisation & UI Refinements

## Architecture
Deeelicious is a Streamlit-based web application with custom HTML/CSS styling via a design token system (`design/tokens.json`, `design/components.css`).
- **Map Component**: Uses Folium (`map_view.py`) rendered via `st_folium` in an iframe.
- **Shop Logos**: SVG vector logos stored in `assets/logos/`, converted to base64 data URIs via `shop_images.py`.
- **Navigation & State**: Streamlit `st.session_state` (`screen`, `detail_shop_id`, `map_selected_shop_id`) and URL query parameters (`st.query_params`).
- **Filter Controls**: Sidebar chips (`st.pills`) and form controls (`st.selectbox`, `st.multiselect`) styled with custom injected CSS rules.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | CartoDB Positron Base Tiles | Update Folium base tiles to modern light CartoDB Positron tiles matching site aesthetic | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Shop Logo Markers | Render shop logos on map pins via Folium DivIcon instead of plain numbers | M1 | ORIGINAL_REQUEST §R1 |
| 3 | #1 Ranked Star Badge | Overlay prominent star badge on the #1 ranked shop pin | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Tokenized Popup Cards | Modernise Folium popup cards adhering strictly to design tokens and components | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Shop Ranking Deduplication | Deduplicate shop rankings in map so #1 primary shop is not overwritten by alternatives | M1 | Survey Finding |
| 6 | Cross-Iframe "View basket" Navigation | Enable popup "View basket →" button to navigate reliably to shop detail screen across sandboxed iframe boundaries | M1 | ORIGINAL_REQUEST §R2 |
| 7 | Query Parameter & Screen Navigation | Enhance `app.py` query parameter handling to process shop navigation and switch screens | M1 | ORIGINAL_REQUEST §R2 |
| 8 | Map Preview Card Synchronization | Ensure the shop card below the map synchronises with clicked pins | M1 | ORIGINAL_REQUEST §R2 |
| 9 | Remove '✓' from Diet/Meat Chips | Remove checkmark from selected Diet and Meat filter chips | M2 | ORIGINAL_REQUEST §R3 |
| 10 | Hover '✕' Indicator on Selected Chips | Display '✕' indicator when hovering over an already-selected chip to signal deselection | M2 | ORIGINAL_REQUEST §R3 |
| 11 | Sort by Cursor & Caret Suppression | Suppress I-beam cursor and caret (`cursor: pointer !important; caret-color: transparent !important;`) on Sort by selectbox | M2 | ORIGINAL_REQUEST §R4 |
| 12 | Allergies Cursor & Caret Suppression | Suppress I-beam cursor and caret on Allergies multiselect input | M2 | ORIGINAL_REQUEST §R4 |
| 13 | Full Pytest Suite Verification | 100% test pass with 0 errors across all existing and new unit tests | M3 | ORIGINAL_REQUEST Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Map Modernisation & Pin Popup Navigation (R1 & R2) | Base tiles, DivIcon logo pins, #1 star badge, tokenized popups, ranking deduplication, cross-iframe navigation, query params, card sync (`map_view.py`, `shop_images.py`, `app.py`, `demo.py`) | none | IN_PROGRESS |
| 2 | Filter Chips Hover-Deselect & Control Cursors (R3 & R4) | Diet/Meat hover-deselect '✕', removal of '✓', Sort by & Allergies pointer cursor and transparent caret (`app.py`, `design/components.css`) | none | PLANNED |
| 3 | Comprehensive Verification & Test Suite (AC) | Pytest test execution, regression tests for map/chips/controls, 100% pass with 0 errors | M1, M2 | PLANNED |

## Interface Contracts
### `shop_images.py` ↔ `map_view.py`
- `logo_data_uri(chain: str) -> str | None`: Returns base64 SVG data URI for chain logo, or `None` if no image exists.
- `_BADGES: dict[str, tuple[str, str]]`: Initials and background token fallback.

### `map_view.py` ↔ `app.py`
- `build_map(ranked_lunches: list[Lunch], all_shops: list[Shop], walking_limit_minutes: float = 10.0) -> folium.Map`: Builds modernised map with CartoDB Positron tiles, DivIcon pins, star badge on rank 1, and tokenized popups.
- Popup navigation: Triggers parent URL query parameter update `?shop=<shop_id>`.
- `app.py`: Ingests `st.query_params.get("shop")`, clears parameter, sets `st.session_state["detail_shop_id"] = shop_id`, sets `st.session_state["screen"] = "detail"`.

### Design Token Conformance
- All colors and typography must use `theme.token()` and `theme.type_css()` or CSS variables `var(--token)`.
- No literal hex colors (e.g. `#[0-9a-fA-F]{6}`) or literal `font-size:` allowed in `UI_FILES` (`app.py`, `map_view.py`, `shop_images.py`, `demo.py`).
- Every `dl-*` class used in code must be defined in `design/components.css`.

## Code Layout
- `map_view.py`: Folium map generation, custom DivIcon markers, popup cards, tile layers.
- `shop_images.py`: Shop logo retrieval and base64 data URI conversion.
- `app.py`: Main application controller, sidebar filters (`st.pills`), query param listener, screen routing.
- `design/tokens.json`: Canonical design tokens.
- `design/components.css`: Global component styles, form control overrides, chip styles.
- `tests/`: Pytest test suite (`test_theme.py`, `test_filters.py`, `test_map_view.py`, etc.).
