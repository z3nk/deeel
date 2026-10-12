# Meal Deal Finder: UI/UX Brief

Oct 12, 2026 · @Neeam R

Design a fast, one-screen lunch finder for UCL students that ranks nearby shops and shows the best main, snack and drink.

## Design constraints

The app is built in Streamlit, a Python tool that makes a local web app from standard widgets, so design with those pieces or the code will not match your Figma.

- **Layout:** one page, a sidebar on the left, a main column on the right. Use `st.columns` for side-by-side blocks, at most 3 across. Mobile is not a priority; design for a laptop at about 1280 px wide.
- **Inputs available:** text box, sliders, checkboxes, toggles, dropdowns, multi-select chips, buttons, file/photo upload, tabs.
- **Hard to build, so avoid:** custom animations, drag and drop, floating or overlapping elements, maps you can pan, pixel-exact custom components.
- **Styling:** colours, fonts and rounded corners can be set through a theme. Cards are simple bordered containers.
- **Speed matters:** results should appear instantly as sliders move, so keep each screen light. No heavy images; use small thumbnails.
- **Who uses it:** a student between lectures, on a 10-minute walk limit, mostly deciding in under 30 seconds.

## Screens

Five screens, with Find as the main one. The first three are needed for the demo; the last two can be rough.

| # | Screen | Purpose | What it shows |
| --- | --- | --- | --- |
| 1 | Find (home) | Set preferences, see ranked shops | Sidebar: price, quality and warm-lunch sliders, diet and allergen chips, loyalty-card toggle, walking limit. Main: ranked shop cards. |
| 2 | Shop detail | See the full basket at one shop | The chosen main, snack and drink, meal deal vs separate price, photo of each label with its date. |
| 3 | Add a photo | Earn credits | Upload box, preview of what was read from the photo, "pending review" confirmation. |
| 4 | My credits | Show balance and rewards | Balance, pending submissions (not yet paid), history, sponsor rewards with cost. |
| 5 | Review queue | Team approves photos | Photo beside the extracted record, approve and reject buttons. Internal, so plain is fine. |

## Result card

Each shop in the ranked list is one card. Design this first, because everything else is built around it.

| Field | Example | Notes |
| --- | --- | --- |
| Rank and shop name | 1. Tesco Express | Chain logo optional |
| Walking time | 4 min walk | From the campus origin |
| Best basket | Chicken wrap + crisps + Coke | Main, snack, drink |
| Price | £3.85 with Clubcard | Show the deal price, and the separate price struck through if the deal is better |
| Deal or separate | Meal deal saves £1.10 | One short line |
| Why this shop | Cheapest, and the wrap is hot | One line, plain words |
| Freshness | Seen 2 days ago | Turns amber after 7 days, grey after 14 |
| Photo thumbnail | Shelf label | Tap to enlarge |
| Unverified tag | Pending review | Only on pending items |

## States to design

Every screen needs these states drawn, not just the happy path.

| State | When it happens | What the user should see |
| --- | --- | --- |
| Empty | First visit, no preferences set | A short prompt: set your preferences on the left |
| Loading | A photo is being read by Claude (a few seconds) | A spinner and "Reading your photo…"; the rest of the page stays usable |
| No results | Filters are too strict | Which filter is the problem, and a one-click way to relax it |
| Pending | Item uploaded, not yet approved | Shown with an "Unverified" tag; no credits yet |
| Stale | Last seen more than 7 days ago | Amber date; over 14 days, hidden from ranking and shown greyed |
| Unknown allergens | Label had no allergen text | "Allergens not checked"; never shown as safe when the user has an allergy |
| Upload failed | Photo unreadable | Plain reason and a retake prompt |
| Credits earned | Admin approves a photo | A small banner with the credits and the reason |

## Rules the interface must follow

- **Allergens are a safety feature.** Show allergen and diet information only when it was printed on the label. Unknown is never displayed as safe. Make the allergen chips prominent, not buried.
- **Always show the evidence.** Every price carries its photo and a last-seen date.
- **Credits are paid only on approval.** Pending uploads appear in the app but show "0 credits, awaiting review". Keep pending and paid balances visibly separate.
- **Sponsors never affect ranking.** Sponsor names appear only on the credits and rewards screen, never on result cards.
- **Say what is a deal and what is not.** Each card states whether the price is the meal deal or the items bought separately.
- **Plain words.** No jargon such as "optimiser" or "status"; use "best basket" and "awaiting review".

## Figma template

I can't create a Figma file from here, so set this up as the starting skeleton. It takes about 10 minutes.

| Setting | Value |
| --- | --- |
| File name | Meal Deal Finder |
| Pages | Cover · Tokens · Components · Screens · States · Handoff |
| Frame size | Desktop, 1280 × 800 |
| Layout | Sidebar 300 px wide, main column fills the rest, 24 px gutters |
| Spacing scale | 4 · 8 · 16 · 24 · 32 |
| Corner radius | 8 px cards, 6 px buttons |
| Type | One font family, three sizes: heading, body, small |
| Colours | Primary, background, card, text, plus status colours: fresh (green), ageing (amber), stale (grey), unverified (blue) |

**Components to build once and reuse:** result card, slider with label, diet and allergen chip, freshness badge, unverified tag, credit banner, upload box, empty-state message.

**Screen frames to create, named exactly:** `1 Find`, `2 Shop detail`, `3 Add photo`, `4 My credits`, `5 Review queue`. Duplicate each for the states above, named like `1 Find / No results`.

Keep the colour palette tied to the Streamlit theme so the code can match it: pick a primary colour, a background and a text colour as hex values.

## Handing off to the code

1. Share the Figma link with edit access for the whole team, and put it in the repo README.
2. Export the primary, background and text hex values so they can go into the Streamlit theme file.
3. Export thumbnails and logos as PNG, and any icons as SVG, into a shared folder.
4. On the Handoff page, mark which components map to which Streamlit widget (slider, multiselect, button, file upload).
5. Review each screen with whoever is building the code before polishing, in case something is hard to build. Do this at least once before the hackathon day.

The full product plan, including how ranking and credits work, is in the Meal Deal Finder: Build Plan doc.
