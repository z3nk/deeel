# Deeelicious: Design Brief for Claude Design

Oct 15, 2026 · @Neeam R · **For: a new app UI + a brand/design system that also works for marketing**

This brief replaces the visual parts of `UI_BRIEF.md` (v3). Functional behaviour in that file still holds; where they disagree (e.g. mobile), this brief wins.

---

## 1. The product in one paragraph

**Deeelicious** finds the best lunch near UCL Bloomsbury. A student sets budget, walking limit, diet, allergies and nutrition targets; the app ranks six nearby shops and builds the best **main + snack + drink** at each, automatically comparing the **meal deal price against buying separately**. Every combination gets a **Deeel score** (0–100). Prices come from **real shelf photos** taken by students (who earn credits once a photo is approved), with gaps in nutrition/ingredients/allergens filled from **Open Food Facts** by barcode or product name.

- **Name:** Deeelicious — three Es, one word, capital D. Never "Delicious", "DEEELICIOUS" in body text, or "Deelicious".
- **Score:** the **Deeel score** (three Es, capital D, "score" lowercase).
- **Live app:** https://deeelicious.streamlit.app · **Shops:** Tesco Express (Tottenham Ct Rd), Sainsbury's Local (Warren St, 21 Hampstead Rd), M&S Food (TCR), Lidl (TCR), Waitrose (Brunswick Centre), Pret A Manger (TCR).

## 2. Audience and moment of use

- **Who:** UCL students, 18–25, many on tight budgets; a meaningful share with allergies, halal/kosher or vegetarian/vegan diets.
- **When:** between lectures, standing in a shop or walking out of one, **on a phone**, deciding in **under 30 seconds**.
- **What they need to see first:** what to buy, where, how much, how far, and whether it's safe for them.

---

## 3. Brand direction — decision for Neeam

Pick one. Each needs to carry both a utility app and loud campus marketing.

| | A. **"Shelf-smart"** (recommended) | B. **"Snack hype"** | C. **"Student co-op"** |
|---|---|---|---|
| Personality | Clever mate who's done the maths | Loud, meme-y, sticker energy | Earnest, community-run, transparent |
| Colour feel | Keep the deep green `#0F7B5F` as anchor + one punchy accent (e.g. receipt-yellow) on warm off-white | Saturated multi-colour, high contrast | Muted greens and kraft-paper neutrals |
| Type feel | Characterful grotesk for headings, clean sans for UI | Chunky display face | Rounded humanist sans |
| Visual device | **Triple-E** as a price-tag/receipt motif; shelf-edge-label shapes | Stickers, emoji, bold outlines | Hand-drawn map pins, photo collage of real shelves |
| Risk | Can drift corporate if the accent is timid | Undermines trust in allergy info | Low stand-out on posters |

**Why A:** the product's core promises are *money* and *safety* — the voice has to be trustworthy enough for allergen info and the Deeel score, but still fun enough for an Instagram story. Shelf-edge labels and receipts are what users literally see in the shop, so they're a natural, ownable visual language.

### Brand basics to define

- **Wordmark / logo:** explore (1) wordmark with the three Es treated as a unit (stacked like price-tag lines, or as a "≡"-style triple bar), (2) a price-tag or shelf-edge-label icon containing "eee", (3) a sandwich/receipt monogram "D". Need: full wordmark, compact mark (works at 32 px as app/favicon), one-colour version, version on the primary green.
- **Colour:** keep `#0F7B5F` as primary unless the chosen direction strongly argues otherwise (it's already in the shipped theme). Propose one accent, warm neutrals, and the full semantic set (§5).
- **Typography:** one display face (headlines, marketing, score numerals) + one UI face (must render well in Streamlit via Google Fonts or the system stack). Tabular numerals required for prices.
- **Iconography:** simple line icons; needs: walk (minutes), hot/cold, meal deal, card/loyalty, camera/upload, credits, map pin, allergen warning, barcode, sample data, "?".
- **Imagery:** real shelf photography (shot by us — see `uploads/`) over stock food photos; illustration only as accents. No photos of people's faces.
- **Shop logos:** we do **not** have permission to use chain logos. The app currently shows a brand-coloured initials badge per chain (T, S, M&S, L, W, P — `shop_images.py`). Design that badge system properly; marketing must not use supermarket logos.

### Voice and microcopy

Short, direct, numbers-first, a bit of wit — never jokey about allergies.

| Situation | Write | Not |
|---|---|---|
| Result headline | "£3.85 at Tesco · 4 min" | "We found a great option for you!" |
| Deal saving | "Meal deal saves £1.70" | "Amazing savings!!" |
| Deal-only item | "meal deal only" | "price unavailable" |
| No results | "Nothing under £4 within 5 min. Try 10 min?" | "No results found." |
| Allergy (always) | "⚠️ computer-read — check the pack" | anything that softens it |
| Sample data | "Sample data — we haven't photographed this shop yet" | hiding it |
| Credits | "+10 credits once approved" | "You've earned 10 credits!" (before approval) |

---

## 4. Hard rules (non-negotiable in every design)

1. **Allergy warning is always visible** wherever allergens appear: short form "⚠️ computer-read — check the pack" on every allergen line, and the full warning on the results page, shop page and sidebar. Not dismissable, not collapsed, not low-contrast.
   Full text: *"Allergen information is read by computer — from our photos of shelf labels and, where a photo didn't show it, from online data (Open Food Facts). It can be wrong or incomplete. Always check the packaging yourself before eating."*
2. **Allergy chips come first** in the controls and are visually distinct (currently red).
3. **Colour is never the only signal.** Map rank colours, Deeel score bands, freshness and warnings all need a text label, number or icon too.
4. **Sample data is labelled** (placeholder shops: Pret, M&S, Lidl, Waitrose until photographed).
5. **"Sponsors never affect ranking"** appears on results; rewards are visually separate from rankings.
6. **Open Food Facts attribution** (ODbL) on results wherever filled data is shown: "Some nutrition data from Open Food Facts".
7. **Credits are paid only on approval** — UI must never show pending credits as earned.
8. **WCAG AA** contrast for all text (4.5:1 body, 3:1 large text and UI components).

---

## 5. Design system scope

Return tokens that map 1:1 to `.streamlit/config.toml` + CSS custom properties (we inject CSS via `st.markdown`).

### Colour tokens (current values → keep, evolve, or replace)

| Token | Use | Current |
|---|---|---|
| `--primary` | Buttons, active states, featured card border, "Best match" | `#0F7B5F` |
| `--bg` | Page background | `#F7F7F4` |
| `--surface` | Cards, sidebar | `#FFFFFF` |
| `--border` | Card/input borders | `#E3E3DE` |
| `--text` / `--text-muted` | Body / secondary | `#1F2328` / `#6B7280` |
| `--accent` | New: marketing + highlights (e.g. savings) | — |
| `--success` / `--warning` / `--danger` / `--info` | Semantic | `#16A34A` / `#D97706` / `#DC2626` / `#2563EB` |
| `--allergen` | Active allergy chip, allergy warnings | `#DC2626` |
| `--rank-1` / `--rank-2` / `--rank-3` / `--rank-out` | Map markers + rank badges | `#16A34A` / `#EAB308` / `#F97316` / `#94A3B8` |
| `--score-high` / `--score-mid` / `--score-low` | Deeel score ≥70 / 50–69 / <50 | `#16A34A` / `#D97706` / `#94A3B8` |
| `--fresh` / `--ageing` / `--stale` | Seen <7 / 7–14 / >14 days | `#16A34A` / `#D97706` / `#9CA3AF` |
| `--sample` | Sample-data badge (dashed outline) | `#475569` on `#F1F5F9` |
| `--unverified` | Pending/unverified tag | `#2563EB` |

Note: `--rank-2` yellow `#EAB308` fails contrast with white text — fix in the system. Provide **light and dark** variants (Streamlit supports both base themes).

### Other tokens

- **Type scale:** display (marketing), H1–H3, body, small, caption, price (tabular), score numeral.
- **Spacing:** 4-pt scale. **Radii:** chip/pill, card, button. **Elevation:** at most 2 levels (Streamlit cards are bordered, not shadowed).

---

## 6. Component inventory (from the shipped app)

Design each with its states. Names match the code so we can map them back.

**Results**
- **Result card** (`render_result_card`): rank number · shop badge + name · "Best match" badge (featured) · "Sample data" badge (dashed) · walk minutes · "main + snack + drink" line · **Deeel score badge** ("Deeel 79", banded colour) + "How it's scored" popover (5 bars: Value 30, Fillingness 25, Ingredient quality 25, Nutrition balance 10, Deal saving 10, plus per-item ingredient reasons like "4 ingredients · preservatives, flavourings") · nutrition line ("1,040 kcal · 31 g protein", optional "partly from Open Food Facts") · allergen line + short warning · price large · strike-through separate price + "Meal deal saves £x" *or* "Bought separately — no deal" *or* "some items are only priced as part of the deal" · freshness badge ("● Seen 3d ago") · "See basket →".
  - Variants: featured (Section A), secondary (Sections B and C), stale (greyed, "Data too old").
- **Section headings:** "Your best option", "More at {shop}", "Other nearby shops".
- **List / Map tabs.**
- **Map** (`map_view.py`, Leaflet/OpenStreetMap): campus marker, numbered rank markers, grey out-of-range markers, dashed walking-radius circle, popup (shop badge, rank, basket, price, deal/separate, sample-data note).

**Controls (sidebar today — see §8 for mobile)**
- Name field (for credits) · **Allergy chips** (Gluten, Milk, Egg, Nuts, Sesame, Soy, Fish, Shellfish) · **Diet chips** (Vegetarian, Vegan, Halal, Kosher) + "Only mains with a printed halal/kosher label" note · **Meat pills** (Chicken, Beef, Pork, Lamb, Turkey, Duck, Fish; none = any) · **Nutrition sliders** (min protein 0–60 g, max kcal 300–1500 where max = no limit) · **Max price** £2–£14 · **Walking limit** 2–30 min · **Hot / Cold / Any** segmented · **Loyalty toggle** (Clubcard/Nectar) · **Sort** (Deeel score, Quality, Distance, Price) · **Team** expander (admin passcode) at the bottom.

**Shop detail** (`screen_detail`): storefront banner photo (optional) · shop badge + name · walk time · sample-data banner (if placeholder) · allergy warning box · Main / Snack / Drink pickers (dropdown labels include price or "meal deal only", "hot", "not in deal", "unverified") · per-item price, allergens + short warning, nutrition with source, freshness · **Deal vs separate** comparison pair (winner highlighted; "Not available" when a deal-only item is picked) · "Reset to best basket" · catalogue table with search + category filter + "Swap in".

**Add photos** (`screen_upload`): shop dropdown · photo type (Main / Snack / Drink / General) · multi-photo upload (HEIC ok) · "Read N photos" · per-photo result card with thumbnail, "filed in uploads/…", notes · **editable table** (Submit, Product, Type, Price, In deal, Temp, kcal, Protein, Allergens (computer-read), Not from this label, Read quality) · deal-sign table · "Use as banner" · submit / discard · task cards (bonus credits, "Take photo", locked shop + type when a task is active).

**My credits:** balance, "awaiting review (estimate)", rewards list with redeem buttons (sponsors are placeholders), history (Approved / Redeemed / Not accepted).

**Review queue (team only):** grouped by photo · thumbnail · per-product ✓ / ✗ · "Approve all from this photo" · "Approve all N clear reads" · "Fill missing allergens / nutrition / ingredients" · "Publish approved data to the live site". Functional, plain is fine.

**Demo tour** (`demo.py`): "?" button top-right · 8 steps with progress, Back/Next, Exit · uses live components.

**Shared bits:** badges/pills, chips (allergy = danger style, diet = primary), freshness badge, unverified tag, sample-data badge, warning box, info box, empty state, toast/flash message, popover, progress bar.

---

## 7. Screens and states

| Screen | Must show | States to design |
|---|---|---|
| Find (list) | Allergy warning, three sections, sponsor + OFF notes | First load, results, **empty** (by cause: no shops in range → "Relax to 15 min"; no mains match diet → "Clear diet filters"; nutrition limits → "Clear nutrition limits"), allergy filter on, sample-data-heavy |
| Find (map) | Same results on map | No results (all grey) |
| Shop detail | Basket, deal vs separate, catalogue | Deal better / separate better / deal unavailable / **deal-only item picked** / sample shop / unverified item |
| Add photos | Pickers, upload, review table | Nothing uploaded, reading (progress), mixed results, unreadable photo error, duplicate photo, task active, submitted |
| My credits | Balance, rewards, history | No name entered, zero balance, can't afford reward |
| Review queue | Grouped records | Locked (passcode), empty, many pending |
| Demo tour | Step content + nav | Each of 8 steps |

---

## 8. Implementation constraints (Streamlit)

- **Realistic:** theme tokens in `config.toml` (primary, background, secondary background, text, font, plus light/dark); custom HTML/CSS injected via `st.markdown(..., unsafe_allow_html=True)` for badges, pills, cards and headings; `st.container(border=True)` cards; `st.columns` (max 3 across); tabs, popovers, expanders, `st.pills`, data editor, sliders, toggles; Google Fonts via a `<link>`/`@import`.
- **Avoid unless clearly worth it:** custom JS components, drag and drop, overlapping/floating elements, complex animation, pixel-perfect layouts (Streamlit's spacing is only partly controllable).
- **Mobile-first (change from v3):** students use this on phones in shops. Streamlit collapses the sidebar on mobile, so design **how controls work on a 390 px screen** — e.g. a compact top filter bar or "Filters" sheet, with the allergy chips reachable in one tap. Desktop (1280 px) is the secondary layout.
- **Performance:** the page reruns on every control change; keep images to thumbnails and the single storefront banner.

---

## 9. Marketing kit

Same tokens, typography and logo as the app.

- **Logo lockups:** horizontal, stacked, mark-only, on light/dark/primary.
- **Instagram post (1080×1080) and story (1080×1920) templates:** price-comparison card ("Meal deal vs separate"), "Deeel of the day" (one result card), "New shop photographed", "Earn credits" call-to-action.
- **A3 campus poster** (UCL noticeboards, Student Centre) with QR code to the live app.
- **Landing page hero** (desktop + mobile): headline, sub, phone screenshot, "Find my lunch" CTA.
- **Pitch deck template** (16:9): title, problem, demo screenshot, how the Deeel score works, data/trust, team.
- **App screenshot frames** (phone + laptop) for the above.

**Headline starters (grounded in real features — refine):**
- "Your meal deal, but with maths."
- "£3.85 or £5.55? We checked the shelf."
- "Lunch ranked out of 100. Meet the Deeel score."
- "Allergy-aware lunch finding — and we'll always tell you to check the pack."
- "Six shops. Ten minutes. One best lunch."
- "Snap a shelf, earn credits."

Claims rules: no "always the cheapest", no "allergen-safe", no supermarket logos, no implied partnerships.

---

## 10. What to send back

1. **Brand:** chosen direction with rationale, logo files (SVG + PNG), colour palette, type pairing.
2. **Tokens** as both a table and JSON, e.g.
   ```json
   {"color": {"primary": "#0F7B5F", "bg": "#F7F7F4", "surface": "#FFFFFF", "text": "#1F2328", "...": "..."},
    "font": {"display": "...", "ui": "..."}, "radius": {"chip": 999, "card": 12}, "space": [4, 8, 12, 16, 24, 32]}
   ```
   plus the exact `config.toml` `[theme]` block (light and dark) and a CSS `:root` variables block.
3. **Component sheet** for §6 with states, annotated with the Streamlit element each maps to.
4. **Screens** for §7 at 390 px (primary) and 1280 px.
5. **Marketing templates** from §9.
6. **Contrast check** of every text/background pair.

---

## 11. Open questions for Neeam

1. Brand direction: A (recommended), B or C?
2. Keep `#0F7B5F` as the primary, or allow the new brand to change it?
3. Is the triple-E device the hero of the logo, or should the logo lead with food (sandwich/receipt)?
4. Mobile-first now — OK to redesign how filters work on phones (moving away from the sidebar)?
5. Should rewards/sponsor slots appear in marketing at all while sponsors are placeholders?
6. Dark mode: required for launch or later?
7. Any UCL/Students' Union branding rules for posters on campus?
