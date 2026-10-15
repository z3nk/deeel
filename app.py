"""
Deeelicious — Streamlit UI.

Screens:
  1. Find       — three-section results (Section A/B/C) + Map view tab
  2. Shop detail — interactive basket swap + full catalogue table
  3. Add photo  — upload, extract, submit for review
  4. My credits — balance, history, mocked rewards
  5. Review queue — approve/reject (team only)
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from streamlit_folium import st_folium

import approval
import ledger
from db import (
    fetch_approved_deals,
    fetch_approved_items,
    fetch_all_shops,
    fetch_all_tasks,
    get_completed_task_ids,
    complete_task,
    get_connection,
    get_user_credit_balance,
    upsert_user,
)
from extract import build_deal, build_item, extract_photo, is_usable
from nutrition_fill import fill_existing, fill_missing
from demo import screen_demo
from deeel import LABELS as DEEEL_LABELS, WEIGHTS as DEEEL_WEIGHTS
from ingredients import assess as assess_ingredients
from admin import is_admin, render_admin_sidebar
from theme import inject_theme
from map_view import build_map
from photo_store import (
    PHOTO_TYPE_LABELS, PHOTO_TYPES, UPLOAD_EXTENSIONS, UPLOAD_ROOT, save_photo, set_storefront,
)
from shop_images import logo_html, storefront_path
from models import Preferences
from optimiser import (
    get_results,
    is_sample,
    shop_deal,
    lunch_deeel,
    hard_filter,
    _row_to_item,
    _row_to_shop,
    _row_to_deal,
)

UPLOAD_DIR = UPLOAD_ROOT
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Deeelicious",
    page_icon="🥪",
    layout="wide",
    initial_sidebar_state="auto",   # expanded on desktop, collapsed on phones
)
inject_theme()   # design system: fonts, :root tokens, .dl-* classes (design/tokens.json)

# ---------------------------------------------------------------------------
# DB + cached data loaders
# ---------------------------------------------------------------------------

@st.cache_resource
def _conn():
    return get_connection()


@st.cache_data(ttl=30)
def _load_data():
    conn = _conn()
    shops  = [_row_to_shop(r)  for r in fetch_all_shops(conn)]
    items  = [_row_to_item(r)  for r in fetch_approved_items(conn)]
    # also include pending items (shown with Unverified tag when no allergen filter)
    pending_rows = conn.execute(
        "SELECT * FROM items WHERE status = 'pending'"
    ).fetchall()
    pending = [_row_to_item(r) for r in pending_rows]
    deals  = [_row_to_deal(r)  for r in fetch_approved_deals(conn)]
    return shops, items + pending, deals


# ---------------------------------------------------------------------------
# User identity
# ---------------------------------------------------------------------------

def _ensure_user():
    conn = _conn()
    handle = st.session_state.get("username", "").strip()
    if not handle:
        return None
    user_id = f"u-{handle.lower().replace(' ', '-')}"
    upsert_user(conn, user_id, handle)
    return user_id


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

ALLERGENS = ["Gluten", "Milk", "Egg", "Nuts", "Sesame", "Soy", "Fish", "Shellfish"]

# Shown wherever allergen data appears
ALLERGY_WARNING_SHORT = "⚠️ computer-read — check the pack"
ALLERGY_WARNING = (
    "⚠️ **Allergen information is read by computer** — from our photos of shelf labels and, "
    "where a photo didn't show it, from online data (Open Food Facts). It can be wrong or "
    "incomplete. **Always check the packaging yourself before eating.**"
)


def _allergen_text(item) -> str:
    """'Allergens: milk, gluten (Open Food Facts) · ⚠️ computer-read — check the pack'."""
    allergens = ", ".join(item.allergens) if item.allergens else "none found on label"
    source = item.external_fields.get("allergens")
    via = f" ({source})" if source else ""
    return f"Allergens: {allergens}{via} · {ALLERGY_WARNING_SHORT}"
DIETS     = ["Vegetarian", "Vegan", "Halal", "Kosher"]
MEATS     = ["Chicken", "Beef", "Pork", "Lamb", "Turkey", "Duck", "Fish"]
KCAL_CAP  = 1500   # slider max = no calorie limit


# Filter widget keys. Allergy chips also appear in the Find screen's filter bar
# (one tap away on phones); that copy has its own key and is kept in sync.
ALLERGY_KEY = "allergens_avoid"
ALLERGY_QUICK_KEY = "allergens_avoid_quick"
DIET_KEY = "diets"


def _allergy_box_html() -> str:
    """The full allergy warning as the design system's .dl-box--allergy (never dismissable)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ALLERGY_WARNING)
    return f'<div class="dl-box dl-box--allergy" role="note">{text}</div>'


_CHIP_ON = {
    "allergy": "background: var(--allergen); border-color: var(--allergen); color: var(--on-primary);",
    "diet": "background: var(--primary); border-color: var(--primary); color: var(--on-primary);",
}
# On-state wording: allergy "No Gluten ✕", diet "Vegan ✓". Added in CSS because pill
# labels must stay fixed: Streamlit derives the widget id from them, so changing a
# label would reset the selection.
_CHIP_BEFORE = {"allergy": '"No "', "diet": None}
_CHIP_AFTER = {"allergy": '" ✕"', "diet": '" ✓"'}


def _chip_state_css(key: str, options: list[str], variant: str) -> str:
    """
    <style> colouring the selected chips of one st.pills group. Streamlit gives
    selected pills no attribute to hook, so target them by position; the off
    state is in design/components.css. Token variables only.
    """
    selected = set(st.session_state.get(key) or [])
    rules = []
    for i, option in enumerate(options, start=1):
        if option not in selected:
            continue
        button = f".st-key-{key} button:nth-child({i})"
        rules.append(f"{button}, {button}:hover {{ {_CHIP_ON[variant]} }}")
        if _CHIP_BEFORE[variant]:
            rules.append(f"{button} p::before {{ content: {_CHIP_BEFORE[variant]}; }}")
        rules.append(f"{button} p::after {{ content: {_CHIP_AFTER[variant]}; }}")
    return f"<style>{' '.join(rules)}</style>" if rules else ""


def _copy_quick_allergies() -> None:
    """on_change for the filter-bar allergy chips: mirror them into the sidebar's."""
    st.session_state[ALLERGY_KEY] = list(st.session_state.get(ALLERGY_QUICK_KEY) or [])


def _apply_pending_resets() -> None:
    """Clear filter widgets requested by result-page buttons, before the widgets render."""
    if st.session_state.pop("_clear_diet_pending", False):
        st.session_state[DIET_KEY] = []
        st.session_state["meats_allowed"] = []
    if st.session_state.pop("_clear_nutrition_pending", False):
        st.session_state["min_protein"] = 0
        st.session_state["max_kcal"] = KCAL_CAP


def render_sidebar() -> Preferences:
    _apply_pending_resets()
    st.sidebar.title("🥪 Deeelicious")

    # Username
    st.sidebar.text_input(
        "Your name (for credits)",
        key="username",
        placeholder="e.g. Alex",
    )
    st.sidebar.divider()

    # Allergens — first control, serious mode (AllergyChip + AllergyWarning)
    with st.sidebar.container(key="dl_allergy_pills"):
        st.markdown(
            '<p class="dl-chip-heading dl-chip-heading--allergy">Allergies — avoid</p>',
            unsafe_allow_html=True,
        )
        avoid = st.pills(
            "Allergies — avoid", ALLERGENS, selection_mode="multi", key=ALLERGY_KEY,
            label_visibility="collapsed",
        ) or []
        if avoid:
            st.caption("Items without allergen info from a printed label are hidden.")
        st.markdown(_allergy_box_html(), unsafe_allow_html=True)
    st.sidebar.divider()

    # Diet + meat — DietChip style
    with st.sidebar.container(key="dl_diet_pills"):
        st.markdown('<p class="dl-chip-heading">Diet</p>', unsafe_allow_html=True)
        diet_flags = st.pills(
            "Diet", DIETS, selection_mode="multi", key=DIET_KEY,
            label_visibility="collapsed",
        ) or []
        certified = [d.lower() for d in diet_flags if d in ("Halal", "Kosher")]
        if certified:
            st.caption(f"Only mains with a printed {' / '.join(certified)} label are shown.")
        meats = st.pills(
            "Meat in main",
            MEATS,
            selection_mode="multi",
            key="meats_allowed",
            help="Only show mains whose label lists these meats. None picked = any.",
        ) or []
        chip_css = (_chip_state_css(ALLERGY_KEY, ALLERGENS, "allergy")
                    + _chip_state_css(DIET_KEY, DIETS, "diet")
                    + _chip_state_css("meats_allowed", MEATS, "diet"))
        if chip_css:
            st.html(chip_css)
    st.sidebar.divider()

    # Nutrition — whole meal totals
    st.sidebar.markdown("**Nutrition (whole meal)**")
    # Defaults via session_state (not value=) so the "Clear" button can reset them
    st.session_state.setdefault("min_protein", 0)
    st.session_state.setdefault("max_kcal", KCAL_CAP)
    min_protein = st.sidebar.slider("Min protein", 0, 60, step=5, format="%d g", key="min_protein")
    max_kcal = st.sidebar.slider("Max calories", 300, KCAL_CAP, step=50, format="%d kcal", key="max_kcal")
    if min_protein or max_kcal < KCAL_CAP:
        st.sidebar.caption("Items without a nutrition label are hidden.")
    st.sidebar.divider()

    # Preferences
    st.sidebar.markdown("**Preferences**")
    max_price = st.sidebar.slider("Max price (£)", 2.0, 14.0, 6.0, step=0.25)
    walk_limit = st.sidebar.slider("Walking limit", 2, 30, 10, format="%d min")
    temp = st.sidebar.radio(
        "Hot or cold main",
        options=["any", "hot", "cold"],
        horizontal=True,
        key="temp_pref",
    )
    st.sidebar.divider()

    # Loyalty
    st.sidebar.markdown("**Loyalty cards**")
    loyalty = st.sidebar.toggle("I have loyalty cards (Clubcard / Nectar)", value=False)
    st.sidebar.divider()

    # Sort
    sort_label = st.sidebar.selectbox(
        "Sort by",
        options=["Deeel score", "Quality", "Distance", "Price (low to high)"],
        key="sort_select",
    )
    sort_map = {"Deeel score": "deeel", "Quality": "quality", "Distance": "distance", "Price (low to high)": "price"}

    return Preferences(
        sort=sort_map[sort_label],
        temperature_pref=temp,
        max_price_gbp=max_price,
        max_walking_minutes=float(walk_limit),
        diet_flags=[d.lower() for d in diet_flags],
        allergens_exclude=[a.lower() for a in avoid],
        meats_allowed=[m.lower() for m in meats],
        min_protein_g=float(min_protein) if min_protein else None,
        max_kcal=float(max_kcal) if max_kcal < KCAL_CAP else None,
        has_clubcard=loyalty,
        has_nectar=loyalty,
    )


def render_filter_bar(prefs: Preferences) -> None:
    """
    Compact filter bar at the top of the Find screen. On phones the sidebar starts
    collapsed, so this keeps the allergy chips one tap away and says what's active.
    """
    active = []
    if prefs.allergens_exclude:
        active.append("avoiding " + ", ".join(prefs.allergens_exclude))
    active += [d.title() for d in prefs.diet_flags]
    if prefs.meats_allowed:
        active.append(" / ".join(m.title() for m in prefs.meats_allowed))
    if prefs.max_price_gbp:
        active.append(f"≤ £{prefs.max_price_gbp:.2f}")
    active.append(f"{prefs.max_walking_minutes:.0f} min walk")

    with st.container(key="dl_filter_bar"):
        summary_col, button_col = st.columns([3, 1], vertical_alignment="center")
        with summary_col:
            st.caption("Filters: " + " · ".join(active))
        with button_col:
            with st.popover("Allergies", use_container_width=True):
                with st.container(key="dl_allergy_pills_quick"):
                    st.markdown(
                        '<p class="dl-chip-heading dl-chip-heading--allergy">Allergies — avoid</p>',
                        unsafe_allow_html=True,
                    )
                    # Mirror the sidebar's chips before rendering (never after)
                    st.session_state[ALLERGY_QUICK_KEY] = list(st.session_state.get(ALLERGY_KEY) or [])
                    st.pills(
                        "Allergies — avoid", ALLERGENS, selection_mode="multi", key=ALLERGY_QUICK_KEY,
                        label_visibility="collapsed",
                        on_change=_copy_quick_allergies,
                    )
                    if quick_css := _chip_state_css(ALLERGY_QUICK_KEY, ALLERGENS, "allergy"):
                        st.html(quick_css)
                    st.markdown(_allergy_box_html(), unsafe_allow_html=True)
                st.caption("More filters (diet, budget, walk, sort): tap › at the top left.")


# ---------------------------------------------------------------------------
# Result card components
# ---------------------------------------------------------------------------

def _freshness_badge(last_seen_str: str) -> str:
    try:
        days = (date.today() - date.fromisoformat(last_seen_str)).days
    except Exception:
        return ""
    if days > 14:
        return f'<span class="dl-badge dl-badge--stale">● Seen {days}d ago</span>'
    if days > 7:
        return f'<span class="dl-badge dl-badge--ageing">● Seen {days}d ago</span>'
    return f'<span class="dl-badge dl-badge--fresh">● Seen {days}d ago</span>'


def _allergen_line(items_list, avoid: list[str]) -> str:
    all_allergens = sorted({a for i in items_list for a in i.allergens})
    allergen_str = ", ".join(all_allergens) if all_allergens else "none found on labels"
    if any(not i.allergens for i in items_list):
        allergen_str += " (some items' allergens unknown)"
    if any("allergens" in i.external_fields for i in items_list):
        allergen_str += " (partly from Open Food Facts / other photos)"
    return f"Allergens: {allergen_str} · {ALLERGY_WARNING_SHORT}"


def _nutrition_line(items_list) -> str:
    """'1,040 kcal · 31 g protein' for the meal, or '' if any value is missing."""
    if any(f in i.external_fields for i in items_list for f in ("kcal", "protein_g")):
        return _nutrition_line_plain(items_list) + " · partly from Open Food Facts / other photos"
    return _nutrition_line_plain(items_list)


def _nutrition_line_plain(items_list) -> str:
    parts = []
    if all(i.kcal is not None for i in items_list):
        parts.append(f"{sum(i.kcal for i in items_list):,.0f} kcal")
    if all(i.protein_g is not None for i in items_list):
        parts.append(f"{sum(i.protein_g for i in items_list):.0f} g protein")
    return " · ".join(parts)


_FIELD_NAMES = {"kcal": "kcal", "protein_g": "protein", "ingredients_text": "ingredients"}


def _sources_text(external: dict) -> str:
    """'kcal, protein: Open Food Facts' — empty when everything came from the label."""
    by_source: dict[str, list[str]] = {}
    for field, source in external.items():
        by_source.setdefault(source, []).append(_FIELD_NAMES.get(field, field))
    return "; ".join(f"{', '.join(fields)}: {source}" for source, fields in by_source.items())


def _keep_sources(original: dict, row: dict) -> dict:
    """Drop a field's source if the reviewer changed its value by hand."""
    sources = dict(original.get("external_fields") or {})
    for field in ("kcal", "protein_g"):
        if field in sources and _clean_number(row[field]) != _clean_number(original.get(field)):
            sources.pop(field)
    return sources


def _fmt_price(item) -> str:
    """'£3.50', or 'meal deal only' when the shelf only showed a meal deal price."""
    return "meal deal only" if item.price_gbp is None else f"£{item.price_gbp:.2f}"


def _separate_total(items_list) -> float | None:
    """Total bought separately, or None if any item is only sold in the meal deal."""
    return None if any(i.price_gbp is None for i in items_list) else sum(i.price_gbp for i in items_list)


def _item_nutrition(item) -> str:
    parts = []
    if item.kcal is not None:
        parts.append(f"{item.kcal:.0f} kcal")
    if item.protein_g is not None:
        parts.append(f"{item.protein_g:.0f} g protein")
    text = " · ".join(parts) or "nutrition not on label"
    if sources := _sources_text({k: v for k, v in item.external_fields.items() if k in ("kcal", "protein_g")}):
        text += f" ({sources})"
    return text


def _deeel_band(total: int) -> str:
    """.dl-score--<band> modifier (score-high / score-mid / score-low tokens)."""
    if total >= 70:
        return "high"
    if total >= 50:
        return "mid"
    return "low"


def _render_deeel(lunch, prefs: Preferences) -> None:
    """Deeel score badge + a popover with the weighted breakdown."""
    d = lunch_deeel(lunch, prefs)
    badge_col, info_col = st.columns([1, 2])
    with badge_col:
        st.markdown(
            f'<span class="dl-score dl-score--{_deeel_band(d.total)}">Deeel {d.total}</span>',
            unsafe_allow_html=True,
        )
    with info_col.popover("How it's scored"):
        for k, weight in DEEEL_WEIGHTS.items():
            pts = weight * d.parts[k]
            st.progress(d.parts[k], text=f"{DEEEL_LABELS[k]}: {pts:.0f} / {weight}")
        st.caption("**Ingredient quality**: fewer processing markers (additive types like emulsifiers, "
                   "preservatives, sweeteners, flavourings) and shorter ingredient lists score higher. "
                   "The main counts double.")
        for label, item in (("Main", lunch.main), ("Snack", lunch.snack), ("Drink", lunch.drink)):
            a = assess_ingredients(item.ingredients_text)
            via = f" · ingredients from {item.external_fields['ingredients_text']}" \
                if "ingredients_text" in item.external_fields else ""
            st.caption(f"{label} · {item.name}: {a.score * 100:.0f}/100 — {a.reason()}{via}")
        if d.partial:
            st.caption("Some label info is missing. Unknown nutrition scores half marks; "
                       "unknown ingredients score below an average label.")


def render_result_card(lunch, rank: int, prefs: Preferences, featured: bool = False, key_prefix: str = ""):
    from models import Lunch

    with st.container(border=True):
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            rank_str = f"#{rank} " if rank > 0 else ""
            badge = ' <span class="dl-badge dl-badge--best">Best match</span>' if featured else ""
            if is_sample(lunch):
                badge += ' <span class="dl-badge dl-badge--sample">Sample data</span>'
            st.markdown(
                f"{logo_html(lunch.shop)}<b>{rank_str}{lunch.shop.name}</b>{badge}",
                unsafe_allow_html=True,
            )
            st.caption(f"{lunch.shop.walking_minutes:.0f} min walk")
            if is_sample(lunch):
                st.caption("⚠️ Sample data — we haven't photographed this shop yet, so these "
                           "products and prices are placeholders.")
            st.markdown(
                f"{lunch.main.name} + {lunch.snack.name} + {lunch.drink.name}"
            )
            st.markdown(
                _allergen_line([lunch.main, lunch.snack, lunch.drink], prefs.allergens_exclude),
                unsafe_allow_html=True,
            )
            _render_deeel(lunch, prefs)
            nutrition = _nutrition_line([lunch.main, lunch.snack, lunch.drink])
            if nutrition:
                st.caption(nutrition)
            if lunch.why:
                st.caption(f"*{lunch.why}*")

        with col2:
            sep_price = _separate_total([lunch.main, lunch.snack, lunch.drink])
            st.markdown(f"### £{lunch.price_gbp:.2f}")
            if lunch.used_deal and sep_price is None:
                st.caption("✅ Meal deal — some items are only priced as part of the deal")
            elif lunch.used_deal and sep_price > lunch.price_gbp:
                st.markdown(
                    f'<span class="dl-card__strike">£{sep_price:.2f} separately</span>',
                    unsafe_allow_html=True,
                )
                st.caption(f"✅ Meal deal saves £{sep_price - lunch.price_gbp:.2f}")
            else:
                st.caption("Bought separately — no deal")
            # Freshness
            oldest = max(
                (
                    (date.today() - date.fromisoformat(i.last_seen)).days
                    for i in [lunch.main, lunch.snack, lunch.drink]
                    if isinstance(i.last_seen, str)
                ),
                default=0,
            )
            st.markdown(_freshness_badge(
                (date.today() - __import__("datetime").timedelta(days=oldest)).isoformat()
            ), unsafe_allow_html=True)

        with col3:
            if st.button("See basket →", key=f"{key_prefix}open_{lunch.shop.shop_id}_{rank}"):
                st.session_state["detail_shop_id"] = lunch.shop.shop_id
                st.session_state[f"why_{lunch.shop.shop_id}"] = lunch.why or ""
                st.session_state["screen"] = "detail"
                st.rerun()


# ---------------------------------------------------------------------------
# Screen 1: Find
# ---------------------------------------------------------------------------

def screen_find(prefs: Preferences):
    shops, items, deals = _load_data()
    primary, alternatives, other_shops = get_results(shops, items, deals, prefs)

    list_tab, map_tab = st.tabs(["List view", "Map view"])

    with list_tab:
        if primary is None:
            # Diagnose which filter is blocking
            filtered = hard_filter(items, prefs)
            in_range = [s for s in shops if s.walking_minutes <= prefs.max_walking_minutes]
            if not in_range:
                st.warning("No shops within your walking limit.")
                if st.button("Relax to 15 min", key="relax_walk"):
                    st.session_state["walk_limit_override"] = 15
                    st.rerun()
            elif not any(i.category == "main" for i in filtered):
                st.warning("No mains match your filters.")
                if st.button("Clear diet filters", key="relax_diet"):
                    st.session_state["_clear_diet_pending"] = True
                    st.rerun()
            elif prefs.min_protein_g is not None or prefs.max_kcal is not None:
                st.warning("No meal near you fits your protein / calorie limits.")
                if st.button("Clear nutrition limits", key="relax_nutrition"):
                    st.session_state["_clear_nutrition_pending"] = True
                    st.rerun()
            else:
                st.info("Set your preferences on the left to find the best lunch near you.")
                st.caption("Pick a budget and walking limit — results appear instantly.")
            return

        in_range_count = sum(1 for s in shops if s.walking_minutes <= prefs.max_walking_minutes)
        st.caption(f"{in_range_count} shops within {int(prefs.max_walking_minutes)} min · sponsors never affect ranking")

        st.caption(ALLERGY_WARNING)

        # Section A — featured best option
        st.markdown("#### Your best option")
        render_result_card(primary, rank=1, prefs=prefs, featured=True)

        # Section B — alternatives at same shop
        if alternatives:
            st.markdown(f"#### More at {primary.shop.name}")
            for i, alt in enumerate(alternatives, start=2):
                render_result_card(alt, rank=i, prefs=prefs, featured=False)

        # Section C — other shops
        if other_shops:
            st.divider()
            st.markdown("#### Other nearby shops")
            for i, lunch in enumerate(other_shops, start=len(alternatives) + 2):
                render_result_card(lunch, rank=i, prefs=prefs, featured=False)

        # Stale shops — greyed
        all_ranked_ids = (
            {primary.shop.shop_id}
            | {l.shop.shop_id for l in alternatives}
            | {l.shop.shop_id for l in other_shops}
        )
        stale_items = [i for i in items
                       if isinstance(i.last_seen, str)
                       and (date.today() - date.fromisoformat(i.last_seen)).days > 14]
        stale_shop_ids = {i.shop_id for i in stale_items} - all_ranked_ids
        if stale_shop_ids:
            st.caption("Not ranked — last seen over 14 days ago")
            for shop in shops:
                if shop.shop_id in stale_shop_ids:
                    st.markdown(
                        f'<div style="opacity:0.4;border:var(--border-width-hairline) solid var(--border);border-radius:var(--radius-button);'
                        f'padding:12px;margin-bottom:8px">'
                        f'{logo_html(shop, size=20)}<b>{shop.name}</b> · {shop.walking_minutes:.0f} min walk · '
                        f'<span style="color:var(--text-muted)">Data too old</span></div>',
                        unsafe_allow_html=True,
                    )

        st.caption("Sponsors never affect ranking. Some nutrition data from "
                   "[Open Food Facts](https://world.openfoodfacts.org) (ODbL), where our photo didn't show it.")

    with map_tab:
        all_ranked = [primary] + alternatives + other_shops if primary else []
        fmap = build_map(
            ranked_lunches=all_ranked,
            all_shops=shops,
            walking_limit_minutes=prefs.max_walking_minutes,
        )
        st_folium(fmap, width=900, height=500, returned_objects=[])


# ---------------------------------------------------------------------------
# Screen 2: Shop detail
# ---------------------------------------------------------------------------

def screen_detail():
    shops, all_items, deals = _load_data()
    shop_id = st.session_state.get("detail_shop_id")
    shop = next((s for s in shops if s.shop_id == shop_id), None)

    if shop is None:
        st.error("Shop not found.")
        if st.button("← Back"):
            st.session_state["screen"] = "find"
            st.rerun()
        return

    if st.button("← Back to results"):
        st.session_state["screen"] = "find"
        st.rerun()

    photo = storefront_path(shop)
    if photo is not None:
        st.image(str(photo))
    st.markdown(f"<h2>{logo_html(shop, size=40)}{shop.name}</h2>", unsafe_allow_html=True)
    # Pull the why from the last ranked result for this shop if available
    why_text = st.session_state.get(f"why_{shop_id}", "")
    if any(i.shop_id == shop_id and i.source_image == "fallback.jpg" for i in all_items):
        st.info("**Sample data.** We haven't photographed this shop yet — the products and "
                "prices below are placeholders, not real readings.")
    sub = f"{shop.walking_minutes:.0f} min walk from campus"
    if why_text:
        sub += f" · {why_text}"
    st.caption(sub)

    # Items for this shop
    shop_items = [i for i in all_items if i.shop_id == shop_id and i.status in ("approved", "pending")]
    mains  = [i for i in shop_items if i.category == "main"]
    snacks = [i for i in shop_items if i.category == "snack"]
    drinks = [i for i in shop_items if i.category == "drink"]
    shop_deals = [d for d in deals if d.shop_id == shop_id]

    if not mains or not snacks or not drinks:
        st.info("Not enough items to build a full basket for this shop yet.")
        return

    # Per-category dropdowns
    def _item_label(item) -> str:
        hot = " · hot" if item.temperature == "hot" else ""
        nd = " · not in deal" if item.meal_deal_eligible is False else ""
        pend = " · unverified" if item.status == "pending" else ""
        return f"{item.name} — {_fmt_price(item)}{hot}{nd}{pend}"

    key_prefix = f"detail_{shop_id}"

    # Apply any pending swaps from the catalogue table BEFORE widgets are instantiated
    for cat in ("main", "snack", "drink"):
        pending = f"{key_prefix}_{cat}_pending"
        if pending in st.session_state:
            st.session_state[f"{key_prefix}_{cat}"] = st.session_state.pop(pending)

    st.warning(ALLERGY_WARNING)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.caption("MAIN")
        main_idx = st.selectbox(
            "Main", range(len(mains)),
            format_func=lambda i: _item_label(mains[i]),
            key=f"{key_prefix}_main",
        )
        main = mains[main_idx]
        st.markdown(f"**{main.name}**")
        if main.temperature == "hot":
            st.caption("🔥 hot")
        st.caption(_fmt_price(main))
        st.caption(_allergen_text(main))
        st.caption(_item_nutrition(main))
        st.markdown(_freshness_badge(str(main.last_seen)), unsafe_allow_html=True)
        if main.status == "pending":
            st.caption("⚠️ Unverified")

    with col2:
        st.caption("SNACK")
        snack_idx = st.selectbox(
            "Snack", range(len(snacks)),
            format_func=lambda i: _item_label(snacks[i]),
            key=f"{key_prefix}_snack",
        )
        snack = snacks[snack_idx]
        st.markdown(f"**{snack.name}**")
        st.caption(_fmt_price(snack))
        st.caption(_allergen_text(snack))
        st.caption(_item_nutrition(snack))
        st.markdown(_freshness_badge(str(snack.last_seen)), unsafe_allow_html=True)

    with col3:
        st.caption("DRINK")
        drink_idx = st.selectbox(
            "Drink", range(len(drinks)),
            format_func=lambda i: _item_label(drinks[i]),
            key=f"{key_prefix}_drink",
        )
        drink = drinks[drink_idx]
        st.markdown(f"**{drink.name}**")
        st.caption(_fmt_price(drink))
        st.caption(_allergen_text(drink))
        st.caption(_item_nutrition(drink))
        st.markdown(_freshness_badge(str(drink.last_seen)), unsafe_allow_html=True)

    # Reset button
    default_idxs = (0, 0, 0)
    current_idxs = (main_idx, snack_idx, drink_idx)
    if current_idxs != default_idxs:
        if st.button("Reset to best basket"):
            for k in [f"{key_prefix}_main", f"{key_prefix}_snack", f"{key_prefix}_drink"]:
                st.session_state[k] = 0
            st.rerun()

    st.divider()

    # Pricing comparison
    sep_price = _separate_total([main, snack, drink])   # None = a deal-only item is picked
    deal_eligible = (
        main.meal_deal_eligible is not False
        and snack.meal_deal_eligible is not False
        and drink.meal_deal_eligible is not False
    )
    deal = shop_deal(shop_deals, shop_id)
    deal_price = deal.price_gbp if deal else None
    is_deal_better = deal_price is not None and deal_eligible and (sep_price is None or deal_price < sep_price)

    pc1, pc2 = st.columns(2)
    with pc1:
        with st.container(border=True):
            st.caption("Meal deal price")
            if deal is None:
                st.markdown("**No deal at this shop**")
            elif not deal_eligible:
                st.markdown(f"**£{deal.price_gbp:.2f}** — not available")
                st.caption("An item you picked isn't in the meal deal.")
            else:
                st.markdown(f"**£{deal.price_gbp:.2f}**")
                if is_deal_better and sep_price is not None:
                    st.caption(f"✅ Best option — saves £{sep_price - deal.price_gbp:.2f}")
                elif is_deal_better:
                    st.caption("✅ Best option")

    with pc2:
        with st.container(border=True):
            st.caption("Bought separately")
            if sep_price is None:
                st.markdown("**Not available**")
                st.caption("An item you picked is only priced as part of the meal deal.")
            else:
                st.markdown(f"**£{sep_price:.2f}**")
            if not is_deal_better and sep_price is not None:
                st.caption("✅ Best option")

    st.divider()

    # Full catalogue table
    st.markdown(f"#### Everything we've seen here")
    st.caption(f"{len(shop_items)} items catalogued from photos")

    search = st.text_input("Search items", placeholder="e.g. wrap, vegan", key=f"{key_prefix}_search")
    cat_filter = st.radio("Category", ["All", "Mains", "Snacks", "Drinks"], horizontal=True, key=f"{key_prefix}_cat")

    cat_map = {"All": None, "Mains": "main", "Snacks": "snack", "Drinks": "drink"}
    filtered = [
        i for i in shop_items
        if (not cat_map[cat_filter] or i.category == cat_map[cat_filter])
        and (not search or search.lower() in i.name.lower())
    ]

    for item in filtered:
        days_old = (date.today() - date.fromisoformat(str(item.last_seen))).days
        opacity = "0.4" if days_old > 14 else "1.0"
        hot_tag = " · 🔥 hot" if item.temperature == "hot" else ""
        nd_tag = " · *not in deal*" if item.meal_deal_eligible is False else ""
        pend_tag = " · ⚠️ unverified" if item.status == "pending" else ""
        allergens = _allergen_text(item).removeprefix("Allergens: ")

        row_cols = st.columns([3, 1, 1, 2, 1, 1])
        with row_cols[0]:
            st.markdown(
                f'<div style="opacity:{opacity}"><b>{item.name}</b>{hot_tag}{nd_tag}{pend_tag}</div>',
                unsafe_allow_html=True,
            )
        with row_cols[1]:
            st.caption(item.category.upper())
        with row_cols[2]:
            st.markdown(_fmt_price(item))
        with row_cols[3]:
            st.caption(allergens)
        with row_cols[4]:
            st.markdown(_freshness_badge(str(item.last_seen)), unsafe_allow_html=True)
        with row_cols[5]:
            cat = item.category
            options = {"main": mains, "snack": snacks, "drink": drinks}[cat]
            try:
                idx = options.index(item)
            except ValueError:
                idx = None
            current_key = f"{key_prefix}_{cat}"
            if idx is not None and st.session_state.get(current_key, 0) == idx:
                st.caption("In basket")
            elif idx is not None:
                if st.button("Swap in", key=f"swap_{item.item_id}"):
                    st.session_state[f"{current_key}_pending"] = idx
                    st.rerun()


# ---------------------------------------------------------------------------
# Screen 3: Add a photo
# ---------------------------------------------------------------------------

def _photo_in_db(conn, rel_path: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM items WHERE source_image = ? UNION SELECT 1 FROM deals WHERE source_image = ?",
        (rel_path, rel_path),
    ).fetchone() is not None


def _read_photos(conn, files, shop_id: str, photo_type: str) -> list[dict]:
    """Save each photo into the shop/type folder and read it with Claude (button press only)."""
    batch = []
    progress = st.progress(0.0, text="Reading photos…")
    for n, f in enumerate(files, start=1):
        entry = {"file": f.name, "shop_id": shop_id, "photo_type": photo_type,
                 "kind": "other", "notes": "", "items": [], "deals": [], "error": None,
                 "duplicate": False}
        try:
            saved = save_photo(shop_id, photo_type, f.getvalue())
            entry["path"], entry["rel_path"] = str(saved.path), saved.rel_path
            if saved.already_existed and _photo_in_db(conn, saved.rel_path):
                entry["duplicate"] = True
            else:
                result = extract_photo(saved.path, shop_id, photo_type)
                entry.update(kind=result.kind, notes=result.notes,
                             # barcode lookups only: name searches are rate-limited (~6s each),
                             # so they run later via the Review queue / --fill-off
                             items=[fill_missing(conn, i, use_name_search=False) for i in result.items],
                             deals=result.deals)
        except Exception as exc:
            entry["error"] = str(exc)
        batch.append(entry)
        progress.progress(n / len(files), text=f"Read {n} of {len(files)} photos")
    progress.empty()
    return batch


_ITEM_COLUMNS = ["include", "name", "category", "price_gbp", "meal_deal_eligible",
                 "temperature", "kcal", "protein_g", "allergens", "filled_from", "confidence"]


def _items_frame(items: list[dict]):
    import pandas as pd
    rows = [{
        "include": is_usable(i),
        "name": i.get("name", ""),
        "category": i.get("category") if i.get("category") in ("main", "snack", "drink") else "main",
        "price_gbp": i.get("price_gbp"),
        "meal_deal_eligible": i.get("meal_deal_eligible"),
        "temperature": i.get("temperature") if i.get("temperature") in ("hot", "cold", "ambient") else "ambient",
        "kcal": i.get("kcal"),
        "protein_g": i.get("protein_g"),
        "allergens": ", ".join(i.get("allergens") or []),
        "filled_from": _sources_text(i.get("external_fields") or {}),
        "confidence": i.get("confidence") or "medium",
    } for i in items]
    return pd.DataFrame(rows, columns=_ITEM_COLUMNS)


def _render_batch(batch: list[dict], nonce: int) -> tuple[dict, dict, dict]:
    """Show each photo's findings as editable tables. Returns edited items/deals/banner choices."""
    edited_items, edited_deals, banners = {}, {}, {}
    for idx, entry in enumerate(batch):
        with st.container(border=True):
            img_col, info_col = st.columns([1, 4])
            with img_col:
                if entry.get("path") and Path(entry["path"]).exists():
                    st.image(entry["path"], width=140)
            with info_col:
                where = f"{entry['shop_id']}/{entry['photo_type']}"
                st.markdown(f"**{entry['file']}** · filed in `uploads/{where}/`")
                if entry["error"]:
                    st.error("We couldn't read this photo. Hold the phone steady so labels are sharp, then retake.")
                    st.caption(f"_{entry['error']}_")
                    continue
                if entry["duplicate"]:
                    st.info("Already uploaded and submitted — skipped.")
                    continue
                found = f"{len(entry['items'])} product(s)"
                if entry["deals"]:
                    found += f", {len(entry['deals'])} meal deal sign(s)"
                st.caption(f"Photo type: {entry['kind']} · found {found}")
                if entry["notes"]:
                    st.caption(f"⚠️ {entry['notes']}")

            if entry["items"]:
                edited_items[idx] = st.data_editor(
                    _items_frame(entry["items"]),
                    key=f"batch_items_{nonce}_{idx}",
                    hide_index=True,
                    num_rows="fixed",
                    use_container_width=True,
                    disabled=["confidence", "filled_from"],
                    column_config={
                        "include": st.column_config.CheckboxColumn("Submit", width="small"),
                        "name": st.column_config.TextColumn("Product", required=True),
                        "category": st.column_config.SelectboxColumn("Type", options=["main", "snack", "drink"], required=True),
                        "price_gbp": st.column_config.NumberColumn("Price", format="£%.2f", min_value=0.0, step=0.05),
                        "meal_deal_eligible": st.column_config.CheckboxColumn("In deal"),
                        "temperature": st.column_config.SelectboxColumn("Temp", options=["hot", "cold", "ambient"]),
                        "kcal": st.column_config.NumberColumn("kcal", min_value=0),
                        "protein_g": st.column_config.NumberColumn("Protein g", min_value=0.0),
                        "allergens": st.column_config.TextColumn("Allergens (computer-read — check)"),
                        "filled_from": st.column_config.TextColumn("Not from this label"),
                        "confidence": st.column_config.TextColumn("Read quality"),
                    },
                )
            if entry["deals"]:
                import pandas as pd
                edited_deals[idx] = st.data_editor(
                    pd.DataFrame([{
                        "include": True,
                        "name": d.get("name") or "Meal Deal",
                        "price_gbp": d.get("price_gbp"),
                        "loyalty_price_gbp": d.get("loyalty_price_gbp"),
                        "loyalty_scheme": d.get("loyalty_scheme"),
                    } for d in entry["deals"]]),
                    key=f"batch_deals_{nonce}_{idx}",
                    hide_index=True,
                    num_rows="fixed",
                    use_container_width=True,
                    column_config={
                        "include": st.column_config.CheckboxColumn("Submit", width="small"),
                        "name": st.column_config.SelectboxColumn("Deal", options=["Meal Deal", "Premium Meal Deal"]),
                        "price_gbp": st.column_config.NumberColumn("Price", format="£%.2f", min_value=0.0),
                        "loyalty_price_gbp": st.column_config.NumberColumn("Card price", format="£%.2f", min_value=0.0),
                        "loyalty_scheme": st.column_config.SelectboxColumn("Card", options=["Clubcard", "Nectar", "other"]),
                    },
                )
            if entry["photo_type"] == "general" and entry["kind"] == "storefront":
                banners[idx] = st.checkbox(
                    "Use as this shop's banner photo", value=True, key=f"batch_banner_{nonce}_{idx}")
    return edited_items, edited_deals, banners


def _clean_number(value):
    """data_editor gives NaN for empty cells."""
    try:
        return None if value is None or value != value else float(value)
    except (TypeError, ValueError):
        return None


def _submit_batch(conn, batch, edited_items, edited_deals, banners, user_id) -> tuple[list[str], list[str]]:
    """Queue every ticked product/deal as pending. Returns (submitted item ids, problems)."""
    submitted, deal_ids, problems = [], [], []
    today = date.today()
    for idx, frame in edited_items.items():
        entry = batch[idx]
        for row_no, row in enumerate(frame.to_dict("records")):
            if not row["include"]:
                continue
            name = (row["name"] or "").strip()
            price = _clean_number(row["price_gbp"])
            in_deal = None if row["meal_deal_eligible"] is None else bool(row["meal_deal_eligible"])
            if not name or (price is None and in_deal is not True):
                problems.append(f"{entry['file']}: '{name or 'unnamed'}' needs a name, and a price "
                                "or 'In deal' ticked — skipped")
                continue
            fields = {
                **entry["items"][row_no],          # keeps ingredients, diet flags, meats, label text
                "name": name,
                "category": row["category"],
                "price_gbp": price,
                "meal_deal_eligible": in_deal,
                "temperature": row["temperature"],
                "kcal": _clean_number(row["kcal"]),
                "protein_g": _clean_number(row["protein_g"]),
                "external_fields": _keep_sources(entry["items"][row_no], row),
                "allergens": [a.strip() for a in (row["allergens"] or "").split(",") if a.strip()],
            }
            try:
                item = build_item(fields, entry["shop_id"], entry["rel_path"], today, user_id)
            except Exception as exc:
                problems.append(f"{entry['file']}: '{name}' couldn't be saved ({exc})")
                continue
            data = item.model_dump()
            data["last_seen"] = item.last_seen.isoformat()
            submitted.append(approval.queue_item(conn, data))
    for idx, frame in edited_deals.items():
        entry = batch[idx]
        for row in frame.to_dict("records"):
            price = _clean_number(row["price_gbp"])
            if not row["include"] or price is None:
                continue
            deal = build_deal({**row, "price_gbp": price,
                               "loyalty_price_gbp": _clean_number(row["loyalty_price_gbp"])},
                              entry["shop_id"], entry["rel_path"], today, user_id)
            data = deal.model_dump()
            data["last_seen"] = deal.last_seen.isoformat()
            deal_ids.append(approval.queue_deal(conn, data))
    for idx, use in banners.items():
        if use:
            set_storefront(batch[idx]["shop_id"], Path(batch[idx]["path"]))
    return submitted + deal_ids, problems


def screen_upload():
    st.markdown("## Add photos")
    st.info(
        "Pick the shop and what's in the photo, then upload one or many photos. "
        "One photo can cover a whole shelf — we'll pick out every product. "
        "Credits are paid once our team approves each product."
    )

    user_id = _ensure_user()
    if not user_id:
        st.warning("Enter your name in the sidebar to earn credits.")

    conn = _conn()
    shops_list = _load_data()[0]
    shop_ids = [s.shop_id for s in shops_list]
    shops_by_id = {s.shop_id: s.name for s in shops_list}

    # Active task from session state
    active_task_id = st.session_state.get("active_task_id")
    active_task = None
    if active_task_id:
        tasks_all = fetch_all_tasks(conn)
        active_task = next((t for t in tasks_all if t["task_id"] == active_task_id), None)

    if flash := st.session_state.pop("upload_flash", None):
        st.success(flash[0])
        for problem in flash[1]:
            st.warning(problem)

    # ── Shop + photo type ───────────────────────────────────────────────────
    if active_task:
        st.markdown(
            f'<div style="border:var(--border-width-strong) solid var(--primary);border-radius:var(--radius-button);padding:var(--space-3);margin-bottom:var(--space-3)">'
            f'<b>Task: {active_task["item_name"]}</b> at {shops_by_id.get(active_task["shop_id"], active_task["shop_id"])}<br>'
            f'<span class="dl-type-small" style="color:var(--text-muted)">{active_task["ask"]}</span></div>',
            unsafe_allow_html=True,
        )
        shop_id = active_task["shop_id"]
        photo_type = active_task["photo_type"] if active_task["photo_type"] in PHOTO_TYPES else "main"
        st.caption(
            f"Shop: **{shops_by_id.get(shop_id, shop_id)}** · "
            f"Photo type: **{PHOTO_TYPE_LABELS[photo_type]}** (set by the task)"
        )
        if st.button("Cancel task", key="cancel_task"):
            st.session_state.pop("active_task_id", None)
            st.rerun()
    else:
        shop_col, type_col = st.columns(2)
        with shop_col:
            shop_id = st.selectbox(
                "Which shop?", shop_ids,
                format_func=lambda sid: shops_by_id[sid], key="upload_shop",
            )
        with type_col:
            photo_type = st.radio(
                "What's in the photo?", PHOTO_TYPES,
                format_func=lambda t: PHOTO_TYPE_LABELS[t],
                horizontal=True, key="upload_type",
            )

    nonce = st.session_state.get("upload_nonce", 0)
    files = st.file_uploader(
        f"Upload photos — they'll be filed under {shops_by_id.get(shop_id, shop_id)} › {PHOTO_TYPE_LABELS[photo_type]}",
        type=UPLOAD_EXTENSIONS,
        accept_multiple_files=True,
        key=f"photo_upload_{nonce}",
        help="Get labels, prices and deal signs in frame. iPhone HEIC photos are fine.",
    )
    if files and st.button(f"Read {len(files)} photo{'s' if len(files) != 1 else ''}", type="primary"):
        st.session_state["upload_batch"] = _read_photos(conn, files, shop_id, photo_type)

    batch = st.session_state.get("upload_batch")
    if batch:
        st.markdown("#### What we found")
        st.caption("Check each product, fix anything wrong, untick anything that isn't right. "
                   "Allergens are read by computer and must be checked against the pack.")
        st.caption(ALLERGY_WARNING)
        edited_items, edited_deals, banners = _render_batch(batch, nonce)
        n_ticked = sum(int(f["include"].sum()) for f in edited_items.values()) + \
                   sum(int(f["include"].sum()) for f in edited_deals.values())
        submit_label = f"Submit {n_ticked} for review"
        if active_task:
            submit_label += f" — complete task (+{active_task['bonus_credits']} bonus credits)"
        sub_col, clear_col = st.columns([3, 1])
        with sub_col:
            if st.button(submit_label, type="primary", disabled=n_ticked == 0 and not banners, key="submit_batch"):
                ids, problems = _submit_batch(conn, batch, edited_items, edited_deals, banners, user_id)
                if active_task and user_id and ids:
                    complete_task(conn, active_task["task_id"], user_id, ids[0])
                    st.session_state.pop("active_task_id", None)
                st.session_state["upload_flash"] = (
                    f"Submitted {len(ids)} for review. They show as unverified until approved.",
                    problems,
                )
                st.session_state.pop("upload_batch", None)
                st.session_state["upload_nonce"] = nonce + 1
                _load_data.clear()
                st.rerun()
        with clear_col:
            if st.button("Discard", key="discard_batch"):
                st.session_state.pop("upload_batch", None)
                st.session_state["upload_nonce"] = nonce + 1
                st.rerun()

    # ── Task cards ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Tasks")
    st.caption("We need a closer photo of these products. Bonus credits for each.")

    tasks = fetch_all_tasks(conn)
    if not tasks:
        st.caption("No tasks right now — check back later.")
    else:
        done_ids = get_completed_task_ids(conn, user_id) if user_id else set()
        cols = st.columns(3)
        for i, task in enumerate(tasks):
            is_done = task["task_id"] in done_ids
            is_active = task["task_id"] == st.session_state.get("active_task_id")
            shop_display = shops_by_id.get(task["shop_id"], task["shop_id"])

            border = ("var(--border-width-strong) solid var(--primary)" if is_active
                      else "var(--border-width-hairline) solid var(--border)")
            bg = "var(--success-tint)" if is_done else ("var(--bg)" if is_active else "var(--surface)")

            with cols[i % 3]:
                st.markdown(
                    f'<div style="border:{border};border-radius:8px;background:{bg};padding:12px;margin-bottom:8px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
                    f'<b>{task["item_name"]}</b>'
                    f'<span class="dl-badge dl-badge--credits">+{task["bonus_credits"]} credits</span>'
                    f'</div>'
                    f'<div class="dl-type-small" style="color:var(--text-muted)">{shop_display}</div>'
                    f'<div class="dl-type-small" style="color:var(--text-muted)">Needed: {task["needed"]}</div>'
                    f'<div class="dl-type-small" style="color:var(--text);margin-top:var(--space-1)">{task["ask"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if is_done:
                    st.markdown(
                        '<span style="color:var(--success-ink);font-weight:700">Done ✓</span>',
                        unsafe_allow_html=True,
                    )
                elif is_active:
                    st.caption("Upload above ↑")
                else:
                    if st.button("Take photo", key=f"task_btn_{task['task_id']}"):
                        st.session_state["active_task_id"] = task["task_id"]
                        st.rerun()


# ---------------------------------------------------------------------------
# Screen 4: My credits
# ---------------------------------------------------------------------------

def screen_credits():
    st.markdown("## My credits")
    user_id = _ensure_user()
    if not user_id:
        st.info("Enter your name in the sidebar to see your credits.")
        return

    conn = _conn()
    handle = st.session_state.get("username", "")
    balance = get_user_credit_balance(conn, user_id)
    pending_est = ledger.get_pending_credits(conn, user_id)

    st.markdown(f"Hello, **{handle}**")

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Ready to spend", f"{balance} credits")
    with c2:
        st.metric("Awaiting review (estimate)", f"{pending_est} credits")
        st.caption("0 credits until approved")

    st.divider()

    # Rewards
    st.markdown("#### Rewards from sponsors")
    rewards = conn.execute("SELECT * FROM rewards").fetchall()
    if rewards:
        for r in rewards:
            rc1, rc2 = st.columns([3, 1])
            with rc1:
                st.markdown(f"**{r['title']}**")
                st.caption(r["sponsor"])
            with rc2:
                can_afford = balance >= r["cost_credits"]
                if st.button(
                    f"{r['cost_credits']} credits",
                    key=f"redeem_{r['reward_id']}",
                    type="primary" if can_afford else "secondary",
                    disabled=not can_afford or r["codes_remaining"] == 0,
                ):
                    code = ledger.redeem_reward(conn, user_id, r["reward_id"])
                    if code:
                        st.success(f"Redeemed! Your code: **{code}**")
                        _load_data.clear()
                        st.rerun()
                    else:
                        st.error("Redemption failed — no codes remaining or insufficient balance.")
    st.caption("ℹ️ Sponsors shown here are placeholders for the demo. Real partnerships come after launch.")

    st.divider()

    # History
    st.markdown("#### History")
    history = ledger.get_credit_history(conn, user_id)
    if not history:
        st.caption("No credit events yet.")
    else:
        # Resolve shop names from ref_ids
        shops_map = {s.shop_id: s.name for s in _load_data()[0]}

        def _ref_to_shop(ref_id: str) -> str:
            row = conn.execute(
                "SELECT shop_id FROM items WHERE item_id = ? UNION SELECT shop_id FROM deals WHERE deal_id = ?",
                (ref_id, ref_id),
            ).fetchone()
            if row:
                return shops_map.get(row[0], row[0])
            return "—"

        STATUS_COLOURS = {
            "earn":     ("var(--success-ink)", "Approved"),
            "spend":    ("var(--primary)", "Redeemed"),
            "reversal": ("var(--danger)", "Not accepted"),
        }

        hdr1, hdr2, hdr3 = st.columns([3, 2, 1])
        hdr1.caption("**Shop**")
        hdr2.caption("**Status**")
        hdr3.caption("**Credits**")

        for event in history:
            colour, label = STATUS_COLOURS.get(event["type"], ("var(--text-muted)", event["type"]))
            shop_name = _ref_to_shop(event["ref_id"]) if event.get("ref_id") else "—"
            sign = "+" if event["credits"] > 0 else ""

            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(shop_name)
            c2.markdown(
                f'<span style="color:{colour};font-weight:600">{label}</span>',
                unsafe_allow_html=True,
            )
            c3.markdown(f"**{sign}{event['credits']}**")


# ---------------------------------------------------------------------------
# Screen 5: Review queue (team only)
# ---------------------------------------------------------------------------

def _review(conn, records: list[dict], action: str) -> int:
    """Approve or reject records. Re-checks admin mode server-side. Returns credits paid."""
    if not is_admin():
        st.error("Admin mode is locked.")
        return 0
    paid = 0
    for r in records:
        if action == "approve":
            paid += approval.approve(conn, r["_id"], r["_type"])
        else:
            approval.reject(conn, r["_id"], r["_type"])
    _load_data.clear()
    return paid


def _record_line(row: dict) -> str:
    if row["_type"] == "deal":
        card = f" · card £{row['loyalty_price_gbp']:.2f}" if row.get("loyalty_price_gbp") else ""
        return f"**{row.get('name', 'Meal Deal')}** (deal sign) · £{row.get('price_gbp', 0):.2f}{card}"
    allergens = json.loads(row.get("allergens") or "[]")
    flag = " · ⚠️ unclear read" if row.get("needs_review") else ""
    return (
        f"**{row.get('name', '')}** · {row.get('category', '').upper()} · "
        f"{'meal deal only' if row.get('price_gbp') is None else f'£{row["price_gbp"]:.2f}'} · "
        f"allergens: {', '.join(allergens) if allergens else 'not on label'} ({ALLERGY_WARNING_SHORT}){flag}"
    )


def screen_review():
    st.markdown("## Review queue")
    if not is_admin():
        st.warning("Team only. Unlock admin mode under **Team** at the bottom of the sidebar.")
        return
    st.caption("Approve or reject submissions. Credits are paid to the submitter on approval.")

    conn = _conn()
    # sqlite3.Row has no .get(); plain dicts let the cards below use defaults
    records = (
        [{**dict(r), "_type": "item", "_id": r["item_id"]} for r in approval.get_pending_items(conn)]
        + [{**dict(r), "_type": "deal", "_id": r["deal_id"]} for r in approval.get_pending_deals(conn)]
    )

    if flash := st.session_state.pop("review_flash", None):
        st.success(flash)

    with st.expander("Publish approved data to the live site"):
        st.caption("Writes every approved real product and meal deal to `seed/approved.json`. "
                   "Commit and push that file; the deployed app loads it on startup.")
        if st.button("Export approved data", key="export_snapshot"):
            if is_admin():
                from snapshot import export_snapshot
                counts = export_snapshot(conn)
                st.session_state["review_flash"] = (
                    f"Exported {counts['items']} product(s) and {counts['deals']} deal(s) to "
                    "seed/approved.json — now commit and push it.")
                st.rerun()

    with st.expander("Fill missing allergens / nutrition / ingredients"):
        st.caption("For every product missing kcal, protein, ingredients or allergens: our own label data "
                   "for the same barcode, then Open Food Facts by barcode, then by product name (strict match; "
                   "the matched product is shown as the source). Open Food Facts allergens are shown with a "
                   "warning and never clear an item for an allergy filter. Name searches are rate-limited, so "
                   "this does 10 products per click — for everything at once run "
                   "`python seed/load_seed.py --fill-off`.")
        if st.button("Fill next 10 products", key="fill_missing"):
            if is_admin():
                with st.spinner("Looking up products (about 6 seconds each)…"):
                    checked, filled = fill_existing(conn, limit=10)
                _load_data.clear()
                st.session_state["review_flash"] = f"Checked {checked} product(s), filled {filled} field(s)."
                st.rerun()

    if not records:
        st.success("Queue is empty — nothing to review.")
        return

    clear = [r for r in records if r["_type"] == "deal" or not r.get("needs_review")]
    top_col, btn_col = st.columns([3, 2])
    top_col.caption(f"{len(records)} pending · {len(clear)} read clearly")
    with btn_col:
        if clear and st.button(f"Approve all {len(clear)} clear reads", type="primary", key="approve_all_clear"):
            paid = _review(conn, clear, "approve")
            st.session_state["review_flash"] = f"Approved {len(clear)} — {paid} credits paid."
            st.rerun()

    # One card per photo, so a whole-shelf upload can be checked and approved together
    shops_map = {s.shop_id: s.name for s in _load_data()[0]}
    by_photo: dict[str, list[dict]] = {}
    for r in records:
        by_photo.setdefault(r["source_image"], []).append(r)

    for photo, rows in by_photo.items():
        with st.container(border=True):
            img_col, info_col = st.columns([1, 2])
            with img_col:
                src = UPLOAD_DIR / photo
                if src.exists():
                    st.image(str(src), use_container_width=True)
                else:
                    st.caption("[photo not on this server]")
            with info_col:
                first = rows[0]
                st.markdown(
                    f"**{shops_map.get(first['shop_id'], first['shop_id'])}** · {len(rows)} from this photo"
                )
                st.caption(
                    f"Uploaded by {first.get('submitted_by') or 'seed walk'} · {first.get('last_seen', '')} · `{photo}`"
                )
                for r in rows:
                    line_col, ap_col, rj_col = st.columns([6, 1, 1])
                    line_col.markdown(_record_line(r))
                    if ap_col.button("✓", key=f"approve_{r['_id']}", help="Approve"):
                        paid = _review(conn, [r], "approve")
                        st.session_state["review_flash"] = f"Approved {r.get('name')} — {paid} credits paid."
                        st.rerun()
                    if rj_col.button("✗", key=f"reject_{r['_id']}", help="Reject"):
                        _review(conn, [r], "reject")
                        st.session_state["review_flash"] = f"Rejected {r.get('name')}."
                        st.rerun()
                if len(rows) > 1:
                    all_col, rej_col = st.columns(2)
                    if all_col.button(f"Approve all {len(rows)} from this photo", key=f"approve_photo_{photo}"):
                        paid = _review(conn, rows, "approve")
                        st.session_state["review_flash"] = f"Approved {len(rows)} — {paid} credits paid."
                        st.rerun()
                    if rej_col.button("Reject all from this photo", key=f"reject_photo_{photo}"):
                        _review(conn, rows, "reject")
                        st.session_state["review_flash"] = f"Rejected {len(rows)}."
                        st.rerun()


# ---------------------------------------------------------------------------
# Navigation + main
# ---------------------------------------------------------------------------

SCREENS = {
    "Find": "find",
    "Add a photo": "upload",
    "My credits": "credits",
}
ADMIN_SCREENS = {"Review queue": "review"}


def main():
    prefs = render_sidebar()
    render_admin_sidebar()

    if "screen" not in st.session_state:
        st.session_state["screen"] = "find"

    # Review queue only appears in the nav once admin mode is unlocked
    screens = {**SCREENS, **ADMIN_SCREENS} if is_admin() else SCREENS

    # Top nav, with the "?" tour button as a narrow last column (top-right corner)
    nav_cols = st.columns([1] * len(screens) + [0.25])
    for col, (label, key) in zip(nav_cols, screens.items()):
        with col:
            if st.button(label, use_container_width=True):
                st.session_state["screen"] = key
                st.rerun()
    with nav_cols[-1]:
        if st.button("?", key="open_demo", help="Take a live tour of the site", use_container_width=True):
            st.session_state["demo_step"] = 0
            st.session_state["screen"] = "demo"
            st.rerun()

    st.divider()

    screen = st.session_state["screen"]

    if screen == "find":
        render_filter_bar(prefs)
        screen_find(prefs)
    elif screen == "detail":
        screen_detail()
    elif screen == "upload":
        screen_upload()
    elif screen == "credits":
        screen_credits()
    elif screen == "review":
        screen_review()
    elif screen == "demo":
        screen_demo(_load_data, render_result_card)


if __name__ == "__main__":
    main()
