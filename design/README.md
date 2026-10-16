# Deeelicious design guide (hackathon edition)

This is the short reference for presenting and shipping UI work quickly.

## Brand modes

- **Hype mode:** results, savings, score, and credits.
- **Serious mode:** allergies, safety warnings, and data attribution.
- Never apply hype styling to safety content.

## Non-negotiables

1. Show the allergy warning anywhere allergens are shown.
2. Keep allergy controls first and visually clear.
3. Never use colour as the only signal.
4. Mark sample/fallback data clearly.
5. Keep rewards visually separate from ranking.
6. Credit Open Food Facts when external nutrition fields are displayed.

## Design system usage

- `design/tokens.json` is the single source of truth.
- Use `.dl-*` classes from `design/components.css` or `var(--token)`.
- Do not hard-code colors or typography values in app code.

## Logo and brandkit

Use only these official files from `/home/runner/work/deeelicious/deeelicious/design/brandkit/`:

- `logo-full.svg` — default logo for docs, splash, and headers
- `logo-icon.svg` — compact mark for badges/favicons
- `logo-text.svg` — wordmark-only lockup

Usage rules:

- Keep clear space around the logo (minimum `space-4` in-app, `space-8` in marketing).
- Keep logo on clean backgrounds only (`bg`, `surface`, or `primary`).
- Do not redraw, restyle, or approximate the logo.

## Implementation notes

- Call `theme.inject_theme()` once near the top of `app.py`.
- For Folium iframe rendering or standalone badges, use `theme.token()` / `theme.type_css()`.
- Keep launch scope to light theme only.
