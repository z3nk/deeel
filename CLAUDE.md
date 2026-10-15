# Deeelicious

Hackathon project: ranks shops near UCL Bloomsbury and builds the best main + snack + drink.
Read PLAN.md first. Read UI_BRIEF.md for the interface.

## Rules
- Python only, SQLite for storage, Streamlit for the UI.
- No scraping. Data comes from in-store photos and a hand-collected seed walk.
- Allergen and diet info comes only from printed label text. Unknown means unsafe.
- Credits are paid only when a record is approved. Pending items are shown but unpaid.
- Never commit .env or the API key.
- Keep the app fast: load the DB once, cache results, call Claude only on button or upload.

## Preferences and controls
- Preferences are set through sidebar controls only: allergen chips, diet chips (incl. Halal, label-only), meat-in-main chips (none picked = any; meat-free = Vegetarian chip), whole-meal min protein / max calories sliders, max price slider, walking limit slider, hot/cold/any toggle, loyalty card toggle, sort dropdown.
- Meat, kcal and protein come from the label like allergens. Unknown = excluded when that filter is on. Meat and diet filters apply to mains only; nutrition limits are whole-meal totals.
- Free-text preference input ("cheap, warm, vegetarian") is a stretch feature. Do not build it until after the 1:30 hackathon gate.
- The sort dropdown (Deeel score / Quality / Distance / Price). Deeel (default) ranks by the 0–100 Deeel score in `deeel.py` (value 30, fillingness 25, ingredient quality 25, nutrition balance 10, deal saving 10; unknown nutrition = 0.5, unknown ingredients = 0.4; ingredient quality = processing-marker types + top-level ingredient count in `ingredients.py`, method in readme) via a shortlisted combination search; the others map to score weights in the optimiser — see PLAN.md.

## Results output
- Results are shown in three sections: one featured best option (Section A), up to 3 alternatives at the same shop varying the main (Section B), up to 3 other shops (Section C).
- The optimiser exposes `get_results(shops, items, deals, prefs) -> (primary, alternatives, other_shops)`.
- Stale items (> 14 days) are excluded from ranking but shown greyed below all sections.

## Photos
- Uploads are filed by `photo_store.py` as `uploads/<shop_id>/<general|main|snack|drink>/<date>_<hash>.jpg`; `source_image` stores that relative path.
- Shop comes from a dropdown, photo type from a radio; both are locked when answering a task (`tasks.photo_type`).
- One photo can yield many products and deal signs (`extract.extract_photo`); the user edits them in a table, and everything is queued as pending.

## Map
- A map view tab sits alongside the list view tab on Screen 1.
- Uses `streamlit-folium` + `folium` with OpenStreetMap tiles. No API key needed.
- Shop markers are coloured by rank: green (#1), yellow (#2), orange (#3+), grey (out of range).
- A dashed circle shows the walking-limit radius (minutes × 80 m/min).

## Claude model
- Use `claude-opus-4-6` for all vision extraction and "why" line generation.
- Call Claude only on button press or file upload — never on a Streamlit re-render.

## User identity
- Name text input in the sidebar sets `st.session_state["username"]` as `user_id`.
- No auth, no passwords. Handle only.
