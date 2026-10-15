Deeelicious finds the best lunch near UCL Bloomsbury: the best main + snack + drink at six nearby shops, meal deal against buying separately, each basket scored 0–100 with the Deeel score. Students use it on a phone, in a shop, and decide in under 30 seconds. The brand is direction B, "Snack hype": loud and sticker-heavy for the fun parts, calm and plain wherever safety is involved.

## Two modes: hype and serious

Decide the mode for every element before styling it.

- **Hype** covers marketing, results, the Deeel score, savings and credits. Use the `display` face, the accents (`accent-yellow`, `accent-violet`, `accent-cyan`), `shadow-sticker`, `border-width-strong` outlines and a slight tilt on stickers.
- **Serious** covers allergy chips, allergy warnings, sample-data labels and the Open Food Facts attribution. Use the `ui` face only, the `allergen*`, `sample*` and `text` colours, hairline borders, and no stickers, no accents, no tilt and no jokes.
- Never put hype styling on a safety surface, even inside a hype card. On a result card the savings sticker is hype; the allergen line next to it stays serious.

## Content fundamentals

- The name is **Deeelicious**: three Es, one word, capital D. Never "Delicious", "Deelicious", or "DEEELICIOUS" in body text. The score is the **Deeel score**: capital D, lowercase "score".
- Lead with numbers. Use plain words and sentence case. Address the reader as "you".
- Be playful about lunch, never about allergies, health or prices being guaranteed.

| Situation | Write | Not |
|---|---|---|
| Result headline | "£3.85 at Tesco · 4 min" | "We found a great option for you!" |
| Deal saving | "Meal deal saves £1.70" | "Amazing savings!!" |
| Deal-only item | "meal deal only" | "price unavailable" |
| No results | "Nothing under £4 within 5 min. Try 10 min?" | "No results found." |
| Allergy (always) | "⚠️ computer-read — check the pack" | anything that softens it |
| Sample data | "Sample data — we haven't photographed this shop yet" | hiding it |
| Credits | "+10 credits once approved" | "You've earned 10 credits!" (before approval) |
| Plain terms | "Best basket", "Awaiting review", "Allergens not checked" | "optimised result", "status: pending", "null allergen data" |

Empty states name the cause and give a one-tap fix: "Relax to 15 min", "Clear diet filters", "Clear nutrition limits".

## Hard rules (every screen, every asset)

1. Show the allergy warning wherever allergens appear: the short form on every allergen line, and the full box on the results page, the shop page and the filters. Never dismissable, collapsed or low-contrast (see AllergyWarning).
2. Put the allergy chips first in the controls, styled with `allergen`.
3. Never use colour as the only signal. Rank markers carry the number; Deeel bands carry the score; freshness carries the days; warnings carry words.
4. Label sample data (Pret, M&S, Lidl and Waitrose until photographed).
5. Show "Sponsors never affect ranking" on results, and keep rewards visually separate from rankings.
6. Wherever filled data appears, credit Open Food Facts (ODbL): "Some nutrition data from Open Food Facts", in `small`.
7. Never show pending credits as earned. Credits pay out only on approval.
8. Meet WCAG AA: 4.5:1 for body text, 3:1 for large text and UI components. Each token's usage note names the backgrounds it passes on; use only those pairs.

## Colour

- `primary` (Deeel green) anchors the brand: primary buttons, active tab, featured card border, "Best match", active diet chips. Put `on-primary` text on it.
- Accents are for hype only. Put `on-accent` (dark) text on `accent-yellow` and `accent-cyan`, never white. Put white on `accent-violet`. The brand palette has no pinks or reds, so `danger` and `allergen` red always mean something.
- Neutrals: page on `bg`, cards on `surface`, body text in `text`, secondary text in `text-muted` (on `surface` or `bg` only, never on tints). `border` is a decorative hairline. Outline chips and custom inputs with `border-strong`.
- Use the `-ink` tokens for text and the base semantic tokens for fills or icons: `success-ink`, `warning-ink`, `allergen-ink`. The fills `success` and `warning` cannot carry white text.
- Map markers use `rank-1`, `rank-2`, `rank-3` and `rank-out`, with a `rank-ink` number label on every marker. The walking-radius circle is dashed in `primary`.
- Deeel score bands use `score-high`, `score-mid` and `score-low`. Freshness uses `fresh`, `ageing` and `stale` on their tints.
- Light theme only for launch. There is no dark mode.

## Typography

- Two Google Fonts. `display` is Bricolage Grotesque (600–800) for marketing headlines, screen and section titles, prices and score numerals. `ui` is Figtree (400/600/700) for everything else, including all safety text.
- Load both in one request: `https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600..800&family=Figtree:wght@400;600;700&display=swap`.
- Set every price and score with `font-variant-numeric: tabular-nums`. Both faces support it.
- Styles: `display` (marketing only), `h1` screen title, `h2` section heading, `h3` card or shop name, `body`, `body-strong`, `price`, `price-sm`, `score-numeral`, `label` (chips, buttons, score badge), `small` (captions, attribution), `caption` (badges). Never set text below 11px.

## Spacing, radii, elevation

- Use the 4-point scale: `space-1` 4 · `space-2` 8 · `space-3` 12 · `space-4` 16 · `space-6` 24 · `space-8` 32. Mobile cards pad with `space-3` and sit in a `space-4` gutter.
- Radii: `radius-chip` for pills, chips and badges; `radius-button` for buttons, inputs and boxes; `radius-card` for cards; `radius-badge` for shop badges and thumbnails.
- Elevation has two levels at most. App cards get a border, not a shadow. `shadow-raised` is only for popovers and the filter sheet; `shadow-sticker` is hype only.

## Layout (Streamlit)

- Design mobile first, at 390px. Desktop at 1280px is secondary. Streamlit collapses the sidebar on phones, so controls live in a compact top filter bar or a "Filters" sheet, with allergy chips one tap away.
- At most 3 columns (`st.columns`). Cards are `st.container(border=True)`. Custom HTML goes through `st.markdown(..., unsafe_allow_html=True)` with `components/bundle.css` injected once per page.
- Avoid custom JS components, drag and drop, floating or overlapping elements and complex animation. Use thumbnails plus one storefront banner, since the page reruns on every change.
- Theme block for `.streamlit/config.toml`:

```toml
[theme]
base = "light"
primaryColor = "#0F7B5F"
backgroundColor = "#F7F7F4"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#1F2328"
font = "sans serif"
```

Figtree and Bricolage Grotesque reach the page through the injected CSS (`@import` at the top of `components.css`) and the `.dl-*` classes.

### In this repo

- `design/tokens.json` is the single source of every value. Edit it, never hex values in Python.
- `theme.py` turns it into CSS. Call `inject_theme()` once per page; it injects the fonts, the `:root` variables, a `.dl-type-<style>` class per type style (`.dl-type-h2`, `.dl-type-price`, …) and `design/components.css`.
- `design/components/<Name>/README.md` holds each component's rules and Streamlit mapping. `preview.html` beside it is a static reference: run `python theme.py` to regenerate `design/tokens.css`, then open it in a browser.
- `DESIGN_BRIEF.md` remains the spec for screens, states and the marketing kit.

## Logo

- A teammate is making the logo. Do not design, draw or approximate one.
- Until it arrives, set the placeholder wordmark "Deeelicious" in `display` at 800, in `text` or `primary` on `bg` or `surface`, and in `on-primary` on `primary`.
- Every layout keeps a logo slot. Keep clear space of at least `space-4` on all sides in the app and `space-8` in marketing. Minimum wordmark height is 20px on screen. Place it only on `bg`, `surface`, `primary` or `accent-yellow`, never over photos or patterns.

## Iconography

- Use simple line icons. These are needed: walk minutes, hot/cold, meal deal, card/loyalty, camera/upload, credits, map pin, allergen warning, barcode, sample data, and "?".
- No icon set is chosen yet. Until one is, use text labels; the only glyphs in use are ⚠️ (allergy warning, fixed copy), ● (freshness) and ✓/✕ (chips, winners).
- Icons that carry meaning need 3:1 contrast against their background.

## Imagery

- Use real shelf photography shot by the team over stock food photos. Illustration is for accents only. No photos of people's faces.
- Shop identity is the initials badge (ShopBadge). Never use supermarket logos, and keep chain badges out of marketing.

## Marketing

- Use the same tokens, type and logo rules as the app. Hype mode is the default; any allergy claim is in serious mode.
- Claims: never "always the cheapest", never "allergen-safe", no supermarket logos, no UCL or Students' Union logos, crests, colours or names as branding, and no implied partnerships. Sponsor slots are allowed but must stay visibly separate from rankings.
- Ground headlines in real features: "Your meal deal, but with maths." · "£3.85 or £5.55? We checked the shelf." · "Lunch ranked out of 100. Meet the Deeel score." · "Six shops. Ten minutes. One best lunch." · "Snap a shelf, earn credits."

## Not synced

From z3nk/deeelicious@e043479. The repo has no token file, font files, logo or icons, and no component library (it is Streamlit/Python). Tokens come from DESIGN_BRIEF.md, UI_BRIEF.md, `.streamlit/config.toml` and the inline styles in `app.py`, `map_view.py` and `shop_images.py`. Fonts are Google-hosted, so there are no files. Components are static, hand-written renditions (no bundle.js). These shades were darkened from the code for AA: `score-*`, `fresh`, `ageing` and `stale`. Rank labels and Sainsbury's initials switched to dark ink. Not covered: the map popup, the upload table, credits, the review queue, the demo tour and marketing templates.
