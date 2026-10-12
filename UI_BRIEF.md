# Meal Deal Finder: UI/UX Brief

Oct 12, 2026 · @Neeam R · **v3 — three-section results, map view, sidebar-only controls**

Design a fast lunch finder for UCL students that ranks nearby shops and shows the best main, snack and drink combination.

---

## Design constraints

The app runs in Streamlit, a Python tool that builds a local web app from standard widgets. Design within these constraints or the code will not match your Figma.

- **Layout:** one page, fixed 300 px sidebar on the left, main column fills the rest. Use `st.columns` for side-by-side blocks within the main column, at most 3 across. Mobile is not a priority; design for a laptop at 1280 px wide.
- **Inputs available:** sliders, checkboxes, toggles, number inputs, dropdowns, buttons, file/photo upload, tabs.
- **No plain text search box on the Find screen.** Preferences are set entirely through sidebar controls. Free-text input is a stretch feature only.
- **Hard to build, so avoid:** custom animations, drag and drop, floating or overlapping elements, pixel-exact custom components.
- **Map is in scope** via `streamlit-folium` (Leaflet + OpenStreetMap, no API key needed). See Screen 1 Map view below.
- **Styling:** colours, fonts and rounded corners are set through a Streamlit theme file. Cards are simple bordered containers.
- **Speed:** sidebar changes trigger an instant re-render; keep all screens light. Thumbnails only, no large images inline.
- **Who uses it:** a student between lectures, on a ~10-minute walk limit, deciding in under 30 seconds.

---

## Screens

Five screens. The first three are required for the demo; screens 4 and 5 can be rough.

| # | Screen | Purpose | What it shows |
|---|--------|---------|---------------|
| 1 | **Find (home)** | Set preferences, see ranked shops | Sidebar: controls. Main: three-section results with List / Map tab toggle. |
| 2 | **Shop detail** | See the full basket at one shop | Chosen main/snack/drink, meal deal vs separate price, label photos with dates. |
| 3 | **Add a photo** | Upload shelf labels, earn credits | Upload box, extracted preview, "pending review" confirmation. |
| 4 | **My credits** | Show balance and rewards | Balance, pending submissions, history, mocked sponsor rewards. |
| 5 | **Review queue** | Team approves photos (internal) | Photo beside extracted record, approve/reject buttons. Plain is fine. |

---

## Screen 1: Find

### Sidebar (300 px, always visible)

Four labelled sections, top to bottom:

**Allergies — avoid** *(safety feature — place first, in red)*
- Chips: Gluten · Milk · Egg · Nuts · Sesame · Soy · Fish · Shellfish
- Active chip: red fill, "No [allergen] ✕" label
- Note below when any chip is active: *"Items with unchecked labels are hidden."*

**Diet**
- Chips: Vegetarian · Vegan · Halal
- Active chip: primary colour fill
- (AND filter — all selected flags must be true)

**Preferences**
- Max price — slider £2–£14, step £0.25
- Walking limit — slider 2–30 min, default 10
- Hot or cold main — segmented control: Any / Hot / Cold

**Loyalty cards**
- Single toggle: "I have loyalty cards (Clubcard, Nectar)"

**Sort by** *(bottom of sidebar)*
- Dropdown: Quality · Distance · Price (low to high)

---

### Main column — two tabs above results

```
┌─────────────────────────────────────────────────────┐
│  [  List view  ]  [  Map view  ]                    │
├─────────────────────────────────────────────────────┤
│  <results content for active tab>                   │
└─────────────────────────────────────────────────────┘
```

Both tabs reflect the same sidebar preferences. Switching tabs does not re-run the search.

---

### List view tab — three-section results layout

Results are split into three sections, shown in order:

---

**Section A: "Your best option" — 1 featured card**

The top-ranked shop's best basket. Visually distinguished from the rest:
- Thicker border in the primary colour (`--primary`)
- Optional: very light primary-tinted background
- Full-size card (same fields as the result card spec below)
- Label: small "Best match" badge in the top-right corner of the card

---

**Section B: "More at [Shop name]" — up to 3 smaller cards**

Sits directly below the featured card. Heading: e.g. *"More at Tesco Express"*

Shows 2–3 alternative baskets at the same shop, varying the main item (e.g. a different wrap or sandwich, paired with the same best snack and drink). These are secondary cards — same fields, slightly reduced visual weight (no coloured border). All expanded and visible by default.

```
More at Tesco Express
┌──────────────────────────────────────────────────────┐
│  Falafel wrap + Sea Salt crisps + Coke Zero          │
│  £3.85  Meal deal · Seen 3 days ago   [See basket →] │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│  Ham sandwich + Walkers + water                      │
│  £4.25 separately · Seen 3 days ago   [See basket →] │
└──────────────────────────────────────────────────────┘
```

---

**Section C: "Other nearby shops" — up to 3 cards**

Below a divider. Heading: *"Other nearby shops"*

Shows the next 3 best-ranked shops, one card each with their single best basket. Same secondary card style as Section B.

```
Other nearby shops
┌──────────────────────────────────────────────────────┐
│  2. Sainsbury's Local · 6 min walk                   │
│  Falafel wrap + fruit pot + Innocent juice           │
│  £4.00  Meal deal · Seen 9 days ago  [See basket →]  │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│  3. Pret A Manger · 3 min walk                       │
│  Tomato soup + banana + filter coffee                │
│  £5.55 separately · Seen 1 day ago   [See basket →]  │
└──────────────────────────────────────────────────────┘
```

---

**Below all sections — stale shops (greyed, not ranked)**

Items last seen more than 14 days ago are excluded from ranking but shown greyed at the bottom with a label: *"Not ranked — last seen over 14 days ago"*

---

**Empty state** (first visit, no preferences set):
> ← Set your preferences on the left to find the best lunch near you.

**No-results state** (filters too strict):
> No shops match your filters. The problem: [specific filter]. [One-click relax button]

---

### Map view tab

An interactive OpenStreetMap map, 900 × 500 px, centred on UCL Main Quad (Gower Street).

**Markers:**
- Campus origin: blue star, labelled "You are here (UCL Main Quad)"
- Each shop: circle marker, coloured by rank:
  - #1 (Section A): green `#16A34A`
  - #2 (Section C, first): yellow `#EAB308`
  - #3+ (Section C, rest): orange `#F97316`
  - Over walking limit / filtered out: grey `#94A3B8`
- Click marker → popup: shop name · walk time · best basket · best price

**Circle overlay:**
- Dashed circle around campus origin = walking-limit radius
- Radius in metres = walking limit (min) × 80 m/min
- Updates when the walking limit slider changes

**Map states:**

| State | What shows |
|-------|-----------|
| No preferences set | All shops as grey markers |
| Preferences set | Ranked shops coloured by rank; filtered shops grey |
| Shop over walking limit | Grey marker, still visible for orientation |
| No shops in range | All grey + message: "Try increasing your walking limit" |

---

## Result card (full spec)

Design this first — it's used in Sections A, B and C (with different visual weight).

```
┌────────────────────────────────────────────────────────────┐
│  1. Tesco Express                            4 min walk     │
│                                                             │
│  Chicken wrap + Sea Salt crisps + Coke Zero                 │
│                                                             │
│  £3.85 with Clubcard  ~~£4.25~~   Meal deal saves £0.40     │
│                                                             │
│  Cheapest option, and the wrap comes hot                    │
│                                                             │
│  Seen 2 days ago  [label thumbnail]   [View full basket →]  │
└────────────────────────────────────────────────────────────┘
```

| Field | Example | Notes |
|-------|---------|-------|
| Rank and shop name | 1. Tesco Express | Chain logo optional. Omit rank number in Section B (same shop). |
| Walking time | 4 min walk | Right-aligned; from campus origin |
| Best basket | Chicken wrap + Sea Salt crisps + Coke Zero | Main · snack · drink |
| Price | £3.85 with Clubcard | Loyalty price prominent; non-loyalty price struck through when deal is better |
| Deal or separate | Meal deal saves £0.40 | One short line |
| Why this shop | Cheapest option, and the wrap comes hot | One line, plain words — written by Claude. Section B/C cards can omit the why line to save space. |
| Freshness | Seen 2 days ago | Green < 7 days · amber 7–14 · grey/hidden > 14 |
| Label thumbnail | Small image 56×56 px | Tap to enlarge |
| Unverified tag | Pending review | Only when item status is pending |

---

## Screen 2: Shop detail

Full breakdown of one shop's basket. Reached by clicking "View full basket →".

```
← Back to results

Tesco Express · 4 min walk · 124–125 Tottenham Court Road

  Meal deal  £3.85 with Clubcard (£4.25 without)   vs   Separate  £5.50
  [Meal deal highlighted as best option]

  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │  [photo]     │  │  [photo]     │  │  [photo]     │
  │  Chicken     │  │  Sea Salt    │  │  Coke Zero   │
  │  Wrap        │  │  Crisps      │  │              │
  │  £2.10 card  │  │  £0.85       │  │  £0.90       │
  │  MAIN · hot  │  │  SNACK       │  │  DRINK       │
  │  Seen 2d ago │  │  Seen 2d ago │  │  Seen 5d ago │
  └──────────────┘  └──────────────┘  └──────────────┘

  Allergens (from label): gluten, milk, egg
  Diet flags: none printed on label
```

---

## Screen 3: Add a photo

```
Your name (for credits)  [________________]

Upload a shelf-label or meal deal sign photo:
  ┌──────────────────────────────────────────────┐
  │      Drag a photo here or click to browse    │
  │             JPG · PNG · WEBP · up to 10 MB   │
  └──────────────────────────────────────────────┘

  [spinner]  Reading your photo… you can keep browsing.

─── What we read ─────────────────────────────────
  Shop: Tesco Express
  Item: Chicken Caesar Wrap
  Price: £2.10
  Allergens: gluten, milk, egg
  Diet flags: none printed
  Confidence: High ✓

  [Submit for review]   [Upload another]

─── After submission ──────────────────────────────
  Sent — awaiting review.
  0 credits for now. You'll earn up to 20 credits once it's approved.

  ⚠ We only report allergen info printed on the label. Always check the packaging.
```

Upload failed state:
> We couldn't read a price label in that photo. Hold the phone steady, fill the frame with the label, and try again.

---

## Screen 4: My credits

```
Hello, Alex                              Balance: 140 credits

  ┌───────────────┐   ┌────────────────────┐
  │  Ready to     │   │  Awaiting review   │
  │  spend        │   │  2 photos          │
  │  140 credits  │   │  0 credits until   │
  │               │   │  approved          │
  └───────────────┘   └────────────────────┘

─── Redeem rewards ────────────────────────────────
  Campus Coffee Co. (placeholder)
  Free small coffee                   100 credits  [Redeem]

  UCL Union (placeholder)
  £1 off your next lunch               30 credits  [Redeem]

  ⓘ Sponsors shown here are placeholders for the demo.

─── History ───────────────────────────────────────
  +20  Tesco wrap label approved          Oct 12
  +5   Confirmed Sainsbury's price        Oct 11
   0   Pret soup label — awaiting review  Oct 12
```

---

## Screen 5: Review queue (internal, plain)

```
Review queue  (3 items pending)

  ┌──────────────────────────────────────────────────────────────┐
  │  [label photo]    Tesco Express                              │
  │                   Chicken Caesar Wrap — Main                 │
  │                   Price: £2.10 · Allergens: gluten, milk     │
  │                   Confidence: High · Submitted by: Alex      │
  │                   Oct 12, 2026                               │
  │                                                              │
  │                   [Approve +20 credits]   [Reject]           │
  └──────────────────────────────────────────────────────────────┘
```

---

## States to design for every screen

| State | When | What to show |
|-------|------|-------------|
| Empty | First visit, no preferences set | Prompt: set controls on the left |
| Loading | Claude reading a photo | Spinner + "Reading your photo…"; rest of page usable |
| No results | Filters too strict | Named filter + one-click relax |
| Pending | Upload awaiting approval | "Unverified" tag; 0 credits shown |
| Stale | Last seen 7–14 days | Amber date; > 14 days greyed below sections |
| Unknown allergens | No allergen text on label | "Allergens not checked" — never shown as safe |
| Upload failed | Photo unreadable | Plain reason + retake prompt |
| Credits earned | Admin approves a photo | Green banner with credits and reason |
| Map: no range | All shops outside walking limit | All grey markers + "Try increasing your walking limit" |

---

## Rules the interface must follow

1. **Allergens are a safety feature.** Show allergen and diet info only when printed on the label. Unknown is never safe. Allergen chips are first in the sidebar, styled in red.
2. **Always show the evidence.** Every price carries its source photo and last-seen date. No price without a date.
3. **Credits paid only on approval.** Pending uploads show "0 credits, awaiting review". Keep pending and paid balances visibly separate.
4. **Sponsors never affect ranking.** Sponsor names appear only on the credits screen, never on result cards.
5. **Always say deal or separate.** Every card states whether the price is the meal deal or items bought separately.
6. **Plain words.** "Best basket" not "optimised result". "Awaiting review" not "status: pending". "Allergens not checked" not "null allergen data".

---

## Figma setup (10 minutes)

### File skeleton

| Setting | Value |
|---------|-------|
| File name | `Meal Deal Finder` |
| Pages | Cover · Tokens · Components · Screens · States · Handoff |
| Frame size | Desktop, 1280 × 800 |
| Layout | Sidebar 300 px · main column 956 px · 24 px gutters |
| Spacing scale | 4 · 8 · 16 · 24 · 32 px |
| Corner radius | 8 px cards · 6 px buttons · 4 px chips |

### Colour tokens

| Token | Purpose | Hex |
|-------|---------|-----|
| `--primary` | Buttons, active tab, featured card border | `#0F7B5F` |
| `--bg` | Page background | `#F7F7F4` |
| `--card` | Card background | `#FFFFFF` |
| `--border` | Card and input borders | `#E3E3DE` |
| `--text` | Body text | `#1F2328` |
| `--text-muted` | Secondary text, dates | `#6B7280` |
| `--fresh` | Freshness: < 7 days | `#16A34A` |
| `--ageing` | Freshness: 7–14 days | `#D97706` |
| `--stale` | Freshness: > 14 days | `#9CA3AF` |
| `--unverified` | Pending tag | `#2563EB` |
| `--allergen` | Allergen chip active state | `#DC2626` |
| `--map-rank1` | Map marker: #1 | `#16A34A` |
| `--map-rank2` | Map marker: #2 | `#EAB308` |
| `--map-rank3` | Map marker: #3+ | `#F97316` |
| `--map-grey` | Map marker: out of range | `#94A3B8` |

### Type scale

| Role | Size | Weight |
|------|------|--------|
| Screen heading | 20 px | 700 |
| Card heading (shop name) | 16 px | 700 |
| Body | 14 px | 400 |
| Small / muted | 12 px | 400 |

### Components to build once and reuse

| Component | Streamlit equivalent |
|-----------|---------------------|
| Featured result card (Section A) | `st.container` with primary border |
| Secondary result card (Sections B & C) | `st.container` with standard border |
| Section heading | `st.subheader` |
| Section divider | `st.divider` |
| Allergen chip | `st.button` styled as chip |
| Diet chip | `st.button` styled as chip |
| Freshness badge | coloured `st.caption` |
| Unverified tag | coloured caption |
| Credit banner | `st.success` / `st.info` |
| Upload box | `st.file_uploader` |
| Empty state | `st.info` with arrow icon |
| Tab bar (List / Map) | `st.tabs` |
| Map | `st_folium` (streamlit-folium) |
| Photo thumbnail 56×56 px | `st.image` with `width=56` |
| Sort dropdown | `st.selectbox` |
| Hot/cold/any control | `st.radio` horizontal |

### Screen frames to create

Name them exactly:

- `1 Find — List view`
- `1 Find — Map view`
- `1 Find — Empty`
- `1 Find — No results`
- `2 Shop detail`
- `3 Add photo — Upload`
- `3 Add photo — Loading`
- `3 Add photo — Preview`
- `3 Add photo — Submitted`
- `3 Add photo — Failed`
- `4 My credits`
- `5 Review queue`

---

## Handing off to code

1. Share the Figma link with **edit access** for the whole team and add it to the repo README.
2. Export `--primary`, `--bg`, `--text`, `--border` hex values into `.streamlit/config.toml`.
3. Export thumbnails and logos as PNG, icons as SVG, into `seed/assets/`.
4. On the **Handoff page**, annotate which Figma component maps to which Streamlit widget (use the table above).
5. Review each screen with the code owner **before** polishing — catch hard-to-build elements early. Do at least one review before hackathon day.

The full ranking logic, credits system and data schema are in `PLAN.md`.
