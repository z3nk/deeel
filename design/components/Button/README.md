Buttons and links for actions; primary for the main action on a screen.

Hand-written; colours from `.streamlit/config.toml`.

- Primary: `primary` fill, `on-primary` text ("Find my lunch", "Submit for review", "Read N photos"). One per view.
- Secondary: `surface`, `border-strong` outline ("Reset to best basket", "Swap in", "Upload another").
- Link: `primary` text, no fill ("See basket →").
- Disabled: `sample-tint` fill with `text-muted` (e.g. "can't afford reward").
- Focus: a 2px `text` outline, offset 2px.
- Label style `label`; radius `radius-button`.

Streamlit: `st.button(type="primary")` / `st.button()`; the theme's `primaryColor` sets the fill.
