The computer-read allergy warning, in full (box) and short (inline) forms; never dismissable.

Hand-written from `ALLERGY_WARNING` / `ALLERGY_WARNING_SHORT` in `app.py` and DESIGN_BRIEF.md §4.

- Full box (`dl-box dl-box--allergy`): `allergen-ink` text and outline on `allergen-tint`. On the results page, the shop page and the filters. Not collapsible, not low-contrast. Text exactly: "Allergen information is read by computer — from our photos of shelf labels and, where a photo didn't show it, from online data (Open Food Facts). It can be wrong or incomplete. Always check the packaging yourself before eating."
- Short form: "⚠️ computer-read — check the pack" in `allergen-ink`, on every allergen line.
- Unknown allergens read "Allergens not checked", never as safe and never blank.
- Serious mode: UI face only, no stickers, no `shadow-sticker`, no accent colours.

Streamlit: `st.markdown` with the classes (`st.warning` cannot be held to these colours).
