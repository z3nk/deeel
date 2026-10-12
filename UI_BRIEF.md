# Meal Deal Finder: UI/UX Brief

Oct 12, 2026 · @Neeam R · **v2 — updated for map view and sidebar-only controls**

Design a fast, one-screen lunch finder for UCL students that ranks nearby shops and shows the best main, snack and drink combination.

---

## Design constraints

The app runs in Streamlit, a Python tool that builds a local web app from standard widgets. Design within these constraints or the code will not match your Figma.

- **Layout:** one page, fixed 300 px sidebar on the left, main column fills the rest. Use `st.columns` for side-by-side blocks within the main column, at most 3 across. Mobile is not a priority; design for a laptop at 1280 px wide.
- **Inputs available:** sliders, checkboxes, toggles, number inputs, dropdowns, buttons, file/photo upload, tabs.
- **No plain text search box on the Find screen.** Preferences are set entirely through sidebar controls (sliders, checkboxes, number inputs). The free-text option is a stretch feature only.
- **Hard to build, so avoid:** custom animations, drag and drop, floating or overlapping elements, pixel-exact custom components.
- **Map is now in scope** via `streamlit-folium` (Leaflet + OpenStreetMap, no API key needed). See Screen 1 Map view below.
- **Styling:** colours, fonts and rounded corners can be set through a Streamlit theme file. Cards are simple bordered containers.
- **Speed:** sidebar changes trigger an instant re-render; keep all screens light. Thumbnails only, no large images inline.
- **Who uses it:** a student between lectures, on a ~10-minute walk limit, deciding in under 30 seconds.

---

## Screens

Five screens. The first three are required for the demo; screens 4 and 5 can be rough.

| # | Screen | Purpose | What it shows |
|---|--------|---------|---------------|
| 1 | **Find (home)** | Set preferences, see ranked shops | Sidebar: controls. Main: List view and Map view as tabs. |
| 2 | **Shop detail** | See the full basket at one shop | Chosen main/snack/drink, meal deal vs separate price, label photos with dates. |
| 3 | **Add a photo** | Upload shelf labels, earn credits | Upload box, extracted preview, "pending review" confirmation. |
| 4 | **My credits** | Show balance and rewards | Balance, pending submissions, history, mocked sponsor rewards. |
| 5 | **Review queue** | Team approves photos (internal) | Photo beside extracted record, approve/reject buttons. Plain is fine. |

---

## Screen 1: Find

### Sidebar (300 px, always visible)

Group controls into three labelled sections:

**Your preferences**
- Price weight — slider 0–5 (label: "Price matters")
- Quality weight — slider 0–5 (label: "Food quality matters")
- Warm food weight — slider 0–5 (label: "I want something hot")
- Max price — number input, £ prefix, default blank (no cap)
- Walking limit — slider 2–20 min, default 10

**Diet**
- Checkboxes: Vegetarian · Vegan · Gluten-free · Halal · Kosher
- (These are AND filters — must all be true)

**Allergens to exclude** *(prominent — safety feature)*
- Checkboxes: Nuts · Gluten · Dairy · Eggs · Soy · Sesame · Fish · Shellfish
- Warning note under the section: *"We only show allergen info printed on the label. Items with unknown allergens are excluded when you set a filter here."*

**Loyalty cards**
- Toggle: I have a Tesco Clubcard
- Toggle: I have a Sainsbury's Nectar card

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

### List view tab

Ranked result cards, one per shop, best first. See **Result card** section below.

Empty state (no preferences set yet):
> Set your preferences on the left to find the best lunch near you.

No-results state (filters too strict):
> No shops match your filters. [Which filter to relax — show the most restrictive one.]

---

### Map view tab

An interactive OpenStreetMap map, 900 × 500 px, centred on the UCL Main Quad (Gower Street).

**Markers:**
- Campus origin: blue star, labelled "You are here (UCL Main Quad)"
- Each shop: circle marker, coloured by rank:
  - #1: green
  - #2: yellow
  - #3+: orange
  - Over walking limit / filtered out: grey
- Click any marker → popup showing: shop name, walking time, best basket summary, best price

**Circle overlay:**
- A dashed circle around the campus origin showing the current walking-limit radius
- Radius in metres = walking limit (minutes) × 80 m/min
- Updates when the walking limit slider changes

**Map states:**

| State | What shows |
|-------|-----------|
| No preferences set | All shops as grey markers (no ranking yet) |
| Preferences set | Ranked shops coloured by rank; filtered shops grey |
| Shop over walking limit | Grey marker, still visible for orientation |
| No shops in range | All grey; message overlay: "Try increasing your walking limit" |

---

## Result card

Design this first. Everything else is built around it.

```
┌────────────────────────────────────────────────────────────┐
│  1. Tesco Express                            4 min walk     │
│                                                             │
│  Chicken wrap + Sea Salt crisps + Coke Zero                 │
│                                                             │
│  £3.85 with Clubcard  ~~£4.25~~    Meal deal saves £0.40    │
│                                                             │
│  Cheapest option, and the wrap comes hot                    │
│                                                             │
│  Seen 2 days ago  [label thumbnail]   [View full basket →]  │
└────────────────────────────────────────────────────────────┘
```

| Field | Example | Notes |
|-------|---------|-------|
| Rank and shop name | 1. Tesco Express | Chain logo optional |
| Walking time | 4 min walk | Right-aligned; from campus origin |
| Best basket | Chicken wrap + Sea Salt crisps + Coke Zero | Main · snack · drink |
| Price | £3.85 with Clubcard | Loyalty price prominent; non-loyalty struck through when deal is better |
| Deal or separate | Meal deal saves £0.40 | One short line |
| Why this shop | Cheapest option, and the wrap comes hot | One line, plain words — written by Claude |
| Freshness | Seen 2 days ago | Green < 7 days · amber 7–14 · grey/hidden > 14 |
| Label thumbnail | Small image | Tap to enlarge; opens the source photo |
| Unverified tag | Pending review | Only when item status is pending |

---

## Screen 2: Shop detail

Full breakdown of one shop's basket. Reached by clicking "View full basket →" on a result card.

```
← Back to results

Tesco Express · 4 min walk · 124–125 Tottenham Court Road

  Meal deal  £3.85 with Clubcard (£4.25 without)     vs     Separate  £5.50

  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │  [photo]     │  │  [photo]     │  │  [photo]     │
  │  Chicken     │  │  Sea Salt    │  │  Coke Zero   │
  │  Wrap        │  │  Crisps      │  │              │
  │  £2.10 card  │  │  £0.85       │  │  £0.90       │
  │  MAIN        │  │  SNACK       │  │  DRINK       │
  │  Seen 2d ago │  │  Seen 2d ago │  │  Seen 5d ago │
  └──────────────┘  └──────────────┘  └──────────────┘

  Allergen info: Contains gluten, milk, egg (from label)
  Diet: No flags printed on label

  [View label photos]
```

---

## Screen 3: Add a photo

```
Your name (for credits)  [________________]

Upload a shelf-label or meal deal sign photo:
  ┌──────────────────────────────────────────────┐
  │      Drag and drop or click to upload        │
  │             JPG · PNG · WEBP                 │
  └──────────────────────────────────────────────┘

  [Reading your photo…  ████░░░░]  (spinner while Claude runs)

─── What we read ─────────────────────────────────
  Shop: Tesco Express
  Name: Chicken Caesar Wrap
  Price: £2.10
  Allergens: gluten, milk, egg
  Diet flags: none printed
  Confidence: High ✓

  [Submit for review]   [Upload another]

─── After submission ──────────────────────────────
  Submitted! Awaiting team review.
  You'll earn up to 10 credits once it's approved.

  ⚠ Allergens not checked — we only report what's on the label.
```

Upload failed state:
> We couldn't read a price label in that photo. Make sure the label is in focus and try again.

---

## Screen 4: My credits

```
Hello, Alex                          Balance: 45 credits

  ┌─────────────┐  ┌──────────────┐
  │  Approved   │  │  Pending     │
  │  40 credits │  │  5 credits   │
  │             │  │  (1 photo)   │
  └─────────────┘  └──────────────┘

─── Redeem rewards ────────────────────────────────
  Campus Coffee Co. (placeholder)
  Free small coffee                   50 credits  [Redeem]

  UCL Union (placeholder)
  £1 off your next lunch              30 credits  [Redeem]

  Sponsors shown here are placeholders for the demo.
  Real partnerships come after launch.

─── History ───────────────────────────────────────
  +10  Tesco wrap label approved     Oct 12
  +5   Confirmed Sainsbury's price   Oct 11
```

---

## Screen 5: Review queue (internal)

Plain layout — this is for the team, not students.

```
Review queue  (3 items pending)

  ┌──────────────────────────────────────────────────────────────┐
  │  [label photo]    Tesco Express                              │
  │                   Chicken Caesar Wrap — Main                 │
  │                   Price: £2.10 · Allergens: gluten, milk     │
  │                   Confidence: High · Submitted by: Alex      │
  │                   Oct 12, 2026                               │
  │                                                              │
  │                   [Approve +10 credits]   [Reject]           │
  └──────────────────────────────────────────────────────────────┘
  ... (more items)
```

---

## States to design for every screen

| State | When | What to show |
|-------|------|-------------|
| Empty | First visit, no preferences set | Prompt: set controls on the left |
| Loading | Claude reading a photo | Spinner + "Reading your photo…"; rest of page usable |
| No results | Filters too strict | Which filter is the problem + one-click relax |
| Pending | Upload awaiting approval | "Unverified" tag; 0 credits, not yet paid |
| Stale | Last seen 7–14 days | Amber date; > 14 days hidden from ranking, shown greyed |
| Unknown allergens | No allergen text on label | "Allergens not checked" — never shown as safe |
| Upload failed | Photo unreadable | Plain reason + retake prompt |
| Credits earned | Admin approves a photo | Small banner with credits and reason |
| Map: no range | All shops outside walking limit | All grey markers + "Try increasing your walking limit" |

---

## Rules the interface must follow

1. **Allergens are a safety feature.** Allergen and diet info only shows when printed on the label. Unknown is never displayed as safe. Allergen checkboxes must be prominent — not buried at the bottom of the sidebar.
2. **Always show the evidence.** Every price carries its source photo and last-seen date. No price without a date.
3. **Credits paid only on approval.** Pending uploads show "0 credits, awaiting review". Keep pending and paid balances visibly separate on the credits screen.
4. **Sponsors never affect ranking.** Sponsor names appear only on the credits screen, never on result cards.
5. **Always say deal or separate.** Each card states whether the price shown is the meal deal or items bought separately.
6. **Plain words.** No jargon: say "best basket" not "optimised result", "awaiting review" not "status: pending", "allergens not checked" not "null allergen data".

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

| Token | Purpose | Suggested hex |
|-------|---------|--------------|
| `--primary` | Buttons, active tab, rank #1 | `#2563EB` (blue) |
| `--bg` | Page background | `#F8FAFC` |
| `--card` | Card background | `#FFFFFF` |
| `--border` | Card and input borders | `#E2E8F0` |
| `--text` | Body text | `#0F172A` |
| `--text-muted` | Secondary text, dates | `#64748B` |
| `--fresh` | Freshness: < 7 days | `#16A34A` |
| `--ageing` | Freshness: 7–14 days | `#D97706` |
| `--stale` | Freshness: > 14 days, filtered | `#94A3B8` |
| `--unverified` | Pending tag | `#3B82F6` |
| `--allergen` | Allergen chip highlight | `#DC2626` |
| `--map-rank1` | Map marker rank #1 | `#16A34A` |
| `--map-rank2` | Map marker rank #2 | `#EAB308` |
| `--map-rank3+` | Map marker rank #3+ | `#F97316` |
| `--map-grey` | Map marker out of range | `#94A3B8` |

### Type scale

| Role | Size | Weight |
|------|------|--------|
| Screen heading | 20 px | 600 |
| Card heading (shop name) | 16 px | 600 |
| Body | 14 px | 400 |
| Small / muted | 12 px | 400 |

### Components to build once and reuse

| Component | Streamlit equivalent |
|-----------|---------------------|
| Result card | `st.container` with border |
| Sidebar slider with label | `st.slider` |
| Diet / allergen checkbox group | `st.checkbox` (one per flag) |
| Loyalty toggle | `st.toggle` |
| Max price input | `st.number_input` |
| Freshness badge | coloured `st.caption` |
| Unverified tag | `st.badge` or coloured caption |
| Credit banner | `st.success` / `st.info` |
| Upload box | `st.file_uploader` |
| Empty state | `st.info` with icon |
| Tab bar (List / Map) | `st.tabs` |
| Map | `st_folium` (streamlit-folium) |
| Photo thumbnail | `st.image` with `width=80` |

### Screen frames to create

Name them exactly so they match the code:

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
2. Export `--primary`, `--bg`, `--text` hex values into `.streamlit/config.toml` (Streamlit theme file).
3. Export thumbnails and logos as PNG, icons as SVG, into `seed/assets/`.
4. On the **Handoff page**, annotate which Figma component maps to which Streamlit widget (use the table above).
5. Review each screen with the code owner **before** polishing — catch hard-to-build elements early. Do at least one review before hackathon day.

The full ranking logic, credits system and data schema are in `PLAN.md`.
