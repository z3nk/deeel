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

import base64
import html
import json
import re
from html import escape
from datetime import date, datetime, timedelta
from functools import lru_cache
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
from hours import is_shop_open, get_formatted_hours
from models import Preferences
from optimiser import (
    get_results,
    is_sample,
    shop_deal,
    lunch_deeel,
    hard_filter,
    best_lunch_for_shop,
    deal_price,
    effective_price,
    separate_price,
    _row_to_item,
    _row_to_shop,
    _row_to_deal,
)

BRAND_DIR = Path(__file__).parent / "assets" / "brand"   # logo exports of design/brandkit/*.svg
UPLOAD_DIR = UPLOAD_ROOT
UPLOAD_DIR.mkdir(exist_ok=True)
# Map popup uses native button to navigate parent

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Deeelicious",
    page_icon=str(BRAND_DIR / "logo-icon-192.png"),
    layout="wide",
    initial_sidebar_state="auto",   # expanded on desktop, collapsed on phones
)
inject_theme()   # design system: fonts, :root tokens, .dl-* classes (design/tokens.json)


@lru_cache(maxsize=1)
def _splash_logo_b64() -> str:
    return base64.b64encode((BRAND_DIR / "logo-icon-192.png").read_bytes()).decode("ascii")


def _splash() -> None:
    """The D logo over the cream page, once per session on first load (CSS fades it out)."""
    if st.session_state.get("_splash_done"):
        return
    st.session_state["_splash_done"] = True
    st.markdown(f'<div class="dl-splash" aria-hidden="true"><img alt="" '
                f'src="data:image/png;base64,{_splash_logo_b64()}"></div>', unsafe_allow_html=True)


_splash()

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
        "SELECT * FROM items WHERE status = 'pending' AND item_id NOT LIKE 'demo-%'"
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
    """'Allergens: milk, gluten (Open Food Facts)'."""
    allergens = ", ".join(item.allergens) if item.allergens else "none found on label"
    source = item.external_fields.get("allergens")
    via = f" ({source})" if source else ""
    return f"Allergens: {allergens}{via}"
DIETS     = ["Vegetarian", "Vegan", "Halal", "Kosher"]
MEATS     = ["Chicken", "Beef", "Pork", "Lamb", "Turkey", "Duck", "Fish"]
KCAL_CAP  = 1500   # slider max = no calorie limit


# Filter widget keys. Allergy chips also appear in the Find screen's filter bar
# (one tap away on phones); that copy has its own key and is kept in sync.
ALLERGY_KEY = "allergens_avoid"
ALLERGY_QUICK_KEY = "allergens_avoid_quick"
DIET_KEY = "diets"


def _allergy_box_html() -> str:
    return ""


_CHIP_ON = {
    "allergy": "background: var(--allergen); border-color: var(--allergen); color: var(--on-primary);",
    "diet": "background: var(--primary); border-color: var(--primary); color: var(--on-primary);",
}
# On-state wording: allergy "No Gluten ✕", diet: no mark when selected, " ✕" on hover to deselect.
_CHIP_BEFORE = {"allergy": '"No "', "diet": None}
_CHIP_AFTER = {"allergy": '" ✕"', "diet": None}
_CHIP_AFTER_HOVER = {"allergy": '" ✕"', "diet": '" ✕"'}


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
        btn = f".st-key-{key} [data-testid='stButtonGroup'] button:nth-of-type({i}), .st-key-{key} button:nth-child({i})"
        rules.append(f"{btn}, {btn}:hover {{ {_CHIP_ON[variant]} }}")
        if _CHIP_BEFORE.get(variant):
            rules.append(f"{btn} p::before {{ content: {_CHIP_BEFORE[variant]}; }}")
        if _CHIP_AFTER.get(variant):
            rules.append(f"{btn} p::after {{ content: {_CHIP_AFTER[variant]}; }}")
        if _CHIP_AFTER_HOVER.get(variant):
            rules.append(f"{btn}:hover p::after {{ content: {_CHIP_AFTER_HOVER[variant]}; }}")
    return f"<style>{' '.join(rules)}</style>" if rules else ""


def _copy_quick_allergies() -> None:
    """on_change for the filter-bar allergy chips: mirror them into the sidebar's."""
    st.session_state[ALLERGY_KEY] = list(st.session_state.get(ALLERGY_QUICK_KEY) or [])


def _apply_pending_resets() -> None:
    """Clear filter widgets requested by result-page buttons, before the widgets render."""
    if st.session_state.pop("_clear_allergy_pending", False):
        # Only from buttons that explicitly say "Clear … allergy filters"
        st.session_state[ALLERGY_KEY] = []
        st.session_state[ALLERGY_QUICK_KEY] = []
    if st.session_state.pop("_clear_diet_pending", False):
        st.session_state[DIET_KEY] = []
        st.session_state["meats_allowed"] = []
        st.session_state["temp_pref"] = "any"
    if st.session_state.pop("_clear_nutrition_pending", False):
        st.session_state["min_protein"] = 0
        st.session_state["max_kcal"] = KCAL_CAP


def render_sidebar() -> Preferences:
    _apply_pending_resets()
    st.sidebar.image(str(BRAND_DIR / "logo-text.png"), width=190)

    # Username
    st.sidebar.text_input(
        "Username",
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
        avoid = st.multiselect(
            "Allergies — avoid", ALLERGENS, key=ALLERGY_KEY,
            label_visibility="collapsed", placeholder="Choose allergies to avoid…",
            select_all=False,
        ) or []
        if avoid:
            st.caption("Items without allergen info from a printed label are hidden.")
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
        chip_css = (_chip_state_css(DIET_KEY, DIETS, "diet")
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
    if "open_now_override" in st.session_state:
        st.session_state["open_now_only"] = st.session_state.pop("open_now_override")
    open_now_only = st.sidebar.toggle("Open now only", value=False, key="open_now_only")
    max_price = st.sidebar.slider("Max price (£)", 2.0, 14.0, 6.0, step=0.25)
    if "walk_limit_override" in st.session_state:
        st.session_state["walk_limit"] = st.session_state.pop("walk_limit_override")
    st.session_state.setdefault("walk_limit", 10)
    walk_limit = st.sidebar.slider("Walking limit", 2, 30, format="%d min", key="walk_limit")
    st.session_state.setdefault("temp_pref", "any")   # default via state: resets write this key
    temp = st.sidebar.segmented_control(
        "Hot or cold main",
        options=["any", "hot", "cold"],
        selection_mode="single",
        format_func=str.capitalize,
        key="temp_pref",
    ) or "any"                                          # deselecting falls back to any
    st.sidebar.divider()

    # Loyalty cards
    st.sidebar.markdown("**Loyalty cards**")
    has_clubcard = st.sidebar.checkbox("Tesco Clubcard", value=True, key="card_clubcard")
    has_nectar = st.sidebar.checkbox("Sainsbury's Nectar", value=True, key="card_nectar")
    has_lidl_plus = st.sidebar.checkbox("Lidl Plus", value=True, key="card_lidl_plus")
    has_sparks = st.sidebar.checkbox("M&S Sparks", value=True, key="card_sparks")
    has_mywaitrose = st.sidebar.checkbox("myWaitrose", value=True, key="card_mywaitrose")
    has_club_pret = st.sidebar.checkbox("Club Pret", value=True, key="card_club_pret")

    sort_label = st.session_state.get("sort_select", "Deeel score")
    sort_map = {"Deeel score": "deeel", "Quality": "quality", "Distance": "distance", "Price (low to high)": "price"}

    return Preferences(
        sort=sort_map.get(sort_label, "deeel"),
        temperature_pref=temp,
        max_price_gbp=max_price,
        max_walking_minutes=float(walk_limit),
        open_now_only=open_now_only,
        diet_flags=[d.lower() for d in diet_flags],
        allergens_exclude=[a.lower() for a in avoid],
        meats_allowed=[m.lower() for m in meats],
        min_protein_g=float(min_protein) if min_protein else None,
        max_kcal=float(max_kcal) if max_kcal < KCAL_CAP else None,
        has_clubcard=has_clubcard,
        has_nectar=has_nectar,
        has_lidl_plus=has_lidl_plus,
        has_sparks=has_sparks,
        has_mywaitrose=has_mywaitrose,
        has_club_pret=has_club_pret,
    )


def render_filter_bar(prefs: Preferences) -> None:
    """Filter bar removed per design request."""
    pass


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
    if days == 0:
        return '<span class="dl-badge dl-badge--fresh">● Seen today</span>'
    return f'<span class="dl-badge dl-badge--fresh">● Seen {days}d ago</span>'


def _allergen_line(items_list, avoid: list[str]) -> str:
    all_allergens = sorted({a for i in items_list for a in i.allergens})
    allergen_str = ", ".join(all_allergens) if all_allergens else "none found on labels"
    return f"Allergens: {allergen_str}"


def _nutrition_line(items_list) -> str:
    """'1,040 kcal · 31 g protein' for the meal, or '' if any value is missing."""
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


def _separate_total(items_list, prefs: Preferences | None = None) -> float | None:
    """Total bought separately, or None if any item is only sold in the meal deal.
    With prefs, items use the card price for the shopper's own loyalty cards."""
    if prefs is not None:
        return separate_price(items_list, prefs)
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


def _render_deeel_breakdown(lunch, d) -> None:
    """The "How it's scored" popover body: weighted parts + per-item ingredient reasons."""
    bars = []
    for k in DEEEL_WEIGHTS:
        pct = max(0.0, min(100.0, d.parts[k] * 100))
        bars.append(
            f'<div class="dl-bar"><div class="dl-bar__label">{escape(DEEEL_LABELS[k])}</div>'
            f'<div class="dl-bar__track"><div class="dl-bar__fill dl-bar__fill--{_deeel_band(round(pct))}" '
            f'style="width:{pct:.1f}%"></div></div></div>'
        )
    st.markdown("".join(bars), unsafe_allow_html=True)
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


def _md_bold(text: str) -> str:
    """**bold** → <strong> for text placed inside raw HTML (markdown isn't parsed there)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _allergy_box() -> str:
    return ""


def _allergen_line_html(items_list, warn: bool = False) -> str:
    """Allergen line. Only the featured card adds the short computer-read warning
    (one per results page, not one per card)."""
    text = _allergen_line(items_list, [])
    warning = (f' · <span class="dl-allergen-line__warn">{escape(ALLERGY_WARNING_SHORT)}</span>'
               if warn else "")
    return f'<div class="dl-allergen-line dl-card__note">{escape(text)}{warning}</div>'


def _deal_html(lunch, prefs: Preferences | None = None) -> str:
    """Deal state for the price row. The savings sticker is the only hype element on the card."""
    sep_price = _separate_total([lunch.main, lunch.snack, lunch.drink], prefs)
    if lunch.used_deal and sep_price is None:
        return '<span class="dl-plain-deal">Meal deal — some items are only priced as part of the deal</span>'
    if lunch.used_deal and sep_price > lunch.price_gbp:
        return (f'<span class="dl-card__strike">£{sep_price:.2f} separately</span>'
                f'<span class="dl-sticker">Meal deal saves £{sep_price - lunch.price_gbp:.2f}</span>')
    return '<span class="dl-plain-deal">Bought separately — no deal</span>'


def render_result_card(lunch, rank: int, prefs: Preferences, featured: bool = False,
                       key_prefix: str = "", show_rank: bool = True):
    """
    ResultCard (design/components/ResultCard): one bordered container holding one HTML
    block, plus the "How it's scored" popover and the "See basket →" button.
    show_rank=False for Section B (alternatives at the same shop), per the spec.
    """
    trio = [lunch.main, lunch.snack, lunch.drink]
    sample = is_sample(lunch)
    d = lunch_deeel(lunch, prefs)

    top = []
    if show_rank and rank > 0:
        top.append(f'<span class="dl-card__rank dl-card__rank--{min(rank, 3)}" '
                   f'aria-label="Rank {rank}">{rank}</span>')
    top.append(logo_html(lunch.shop))
    top.append(f'<span class="dl-card__name">{escape(lunch.shop.name)}</span>')
    if featured:
        top.append('<span class="dl-badge dl-badge--best">Best match</span>')
    if sample:
        top.append('<span class="dl-badge dl-badge--sample">Sample data</span>')
    is_open = is_shop_open(lunch.shop.shop_id)
    badge_cls = "dl-badge--open" if is_open else "dl-badge--closed"
    status_text = "Open Now" if is_open else "Closed"
    top.append(f'<span class="dl-badge {badge_cls}">{status_text}</span>')
    hours_str = get_formatted_hours(lunch.shop.shop_id)
    if hours_str:
        top.append(f'<span class="dl-card__hours">{escape(hours_str)}</span>')
    top.append(f'<span class="dl-card__walk">{lunch.shop.walking_minutes:.0f} min walk</span>')

    body = [f'<div class="dl-card__top">{"".join(top)}</div>']
    body.append(f'<div class="dl-card__basket">{escape(" + ".join(i.name for i in trio))}</div>')
    nutrition = _nutrition_line(trio)
    if nutrition:
        body.append(f'<div class="dl-card__meta">{escape(nutrition)}</div>')
    body.append(_allergen_line_html(trio, warn=featured))
    if lunch.why:
        body.append(f'<div class="dl-card__meta dl-card__note"><em>{escape(lunch.why)}</em></div>')

    oldest = max(
        ((date.today() - date.fromisoformat(i.last_seen)).days for i in trio if isinstance(i.last_seen, str)),
        default=0,
    )
    fresh = _freshness_badge((date.today() - timedelta(days=oldest)).isoformat())

    price_cls = "dl-card__price" if featured else "dl-card__price dl-card__price--sm"
    body.append(f'<div class="dl-card__price-row"><span class="{price_cls}">£{lunch.price_gbp:.2f}</span>'
                f'{_deal_html(lunch, prefs)}{fresh}</div>')

    card_cls = "dl-card dl-card--in-st" + (" dl-card--featured" if featured else "")
    with st.container(border=True):
        st.markdown(f'<div class="{card_cls}">{"".join(body)}</div>', unsafe_allow_html=True)
        # One row on every width (CSS stops Streamlit stacking it on phones); the
        # basket action is a link-style button, as in the ResultCard spec
        band = _deeel_band(d.total)
        with st.container(key=f"{key_prefix}dl_card_actions_{lunch.shop.shop_id}_{rank}_{band}"):
            score_col, basket_col = st.columns(2)
        with score_col.popover(f"Deeel score {d.total}"):
            _render_deeel_breakdown(lunch, d)
        with basket_col:
            if st.button("View basket →", key=f"{key_prefix}open_{lunch.shop.shop_id}_{rank}",
                         type="tertiary"):
                st.session_state["detail_shop_id"] = lunch.shop.shop_id
                st.session_state[f"why_{lunch.shop.shop_id}"] = lunch.why or ""
                st.session_state["screen"] = "detail"
                st.rerun()


def _section_title(text: str) -> None:
    st.markdown(f'<div class="dl-type-h2 dl-section-title" role="heading" aria-level="2">'
                f'{escape(text)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Screen 1: Find
# ---------------------------------------------------------------------------

def screen_find(prefs: Preferences):
    open_now = bool(getattr(prefs, "open_now_only", False))
    shops, items, deals = _load_data()
    sort_map = {"Deeel score": "deeel", "Quality": "quality", "Distance": "distance", "Price (low to high)": "price"}
    primary, alternatives, other_shops = get_results(shops, items, deals, prefs)

    st.markdown('<h1 class="dl-type-h1 dl-find-title">A deeel for you</h1>', unsafe_allow_html=True)
    list_tab, map_tab = st.tabs(["List view", "Map view"])

    with list_tab:
        top_left, top_right = st.columns([3, 2], vertical_alignment="center")
        with top_left:
            in_range_shops = [s for s in shops if s.walking_minutes <= prefs.max_walking_minutes and (not open_now or is_shop_open(s.shop_id))]
            in_range_count = len(in_range_shops)
            open_suffix = " open" if open_now else ""
            st.caption(f"{in_range_count} shops{open_suffix} within {int(prefs.max_walking_minutes)} min · sponsors never affect ranking")
        with top_right:
            selected_sort = st.selectbox(
                "Sort by",
                options=["Deeel score", "Quality", "Distance", "Price (low to high)"],
                key="sort_select",
            )
            desired_sort = sort_map.get(selected_sort, "deeel")
            if prefs.sort != desired_sort:
                prefs = prefs.model_copy(update={"sort": desired_sort})
                primary, alternatives, other_shops = get_results(shops, items, deals, prefs)

        if primary is None:
            # Diagnose which filter is blocking
            filtered = hard_filter(items, prefs)
            in_range = [s for s in shops if s.walking_minutes <= prefs.max_walking_minutes and (not open_now or is_shop_open(s.shop_id))]
            if not in_range:
                if open_now:
                    st.info("No shops open within your walking limit.")
                    if st.button("Show closed shops too", key="disable_open_now"):
                        st.session_state["open_now_override"] = False
                        st.rerun()
                else:
                    st.info("No shops within your walking limit.")
                if st.button("Relax to 15 min", key="relax_walk"):
                    st.session_state["walk_limit_override"] = 15
                    st.rerun()
            elif not any(i.category == "main" for i in filtered):
                has_diet = any(prefs.diet_flags) or bool(prefs.meats_allowed)
                has_allergy = bool(prefs.allergens_exclude)
                if has_diet and has_allergy:
                    msg = "No mains match your diet and allergy filters."
                    btn_text = "Clear diet & allergy filters"
                elif has_allergy:
                    msg = "No mains match your allergy filters."
                    btn_text = "Clear allergy filters"
                else:
                    msg = "No mains match your diet filters."
                    btn_text = "Clear diet filters"
                st.info(msg)
                if st.button(btn_text, key="relax_diet"):
                    # Each button clears exactly what its label says
                    st.session_state["_clear_diet_pending"] = has_diet or not has_allergy
                    st.session_state["_clear_allergy_pending"] = has_allergy
                    st.rerun()
            elif not any(i.category == "snack" for i in filtered) or not any(i.category == "drink" for i in filtered):
                st.info("No snacks or drinks match your allergy filters.")
                if st.button("Clear allergy filters", key="relax_snack_drink"):
                    st.session_state["_clear_allergy_pending"] = True
                    st.rerun()
            elif prefs.min_protein_g is not None or prefs.max_kcal is not None:
                st.info("No meal near you fits your protein / calorie limits.")
                if st.button("Clear nutrition limits", key="relax_nutrition"):
                    st.session_state["_clear_nutrition_pending"] = True
                    st.rerun()
            else:
                st.info("No meal combinations match your budget or preferences.")
                # Allergy filters are never cleared by a button that doesn't name them
                if st.button("Clear diet & nutrition filters", key="relax_all"):
                    st.session_state["_clear_diet_pending"] = True
                    st.session_state["_clear_nutrition_pending"] = True
                    st.rerun()
            return

        # Section A — featured best option
        _section_title("Your best option")
        render_result_card(primary, rank=1, prefs=prefs, featured=True)

        # Section B — alternatives at same shop (no rank badge, per the ResultCard spec)
        if alternatives:
            _section_title(f"More at {primary.shop.name}")
            for i, alt in enumerate(alternatives, start=2):
                render_result_card(alt, rank=i, prefs=prefs, featured=False, show_rank=False)

        # Section C — other shops
        if other_shops:
            _section_title("Other nearby shops")
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
        stale_shop_objs = [s for s in shops if s.shop_id in stale_shop_ids and (not open_now or is_shop_open(s.shop_id))]
        if stale_shop_objs:
            # Stale card (ResultCard spec): sample-tint, no opacity dimming (that failed contrast)
            cards = "".join(
                f'<div class="dl-card dl-card--stale"><div class="dl-card__top">{logo_html(shop, size=20)}'
                f'<span class="dl-card__name">{escape(shop.name)}</span>'
                f'<span class="dl-badge dl-badge--stale">Data too old</span>'
                f'<span class="dl-badge {"dl-badge--open" if is_shop_open(shop.shop_id) else "dl-badge--closed"}">{"Open Now" if is_shop_open(shop.shop_id) else "Closed"}</span>'
                f'<span class="dl-card__hours">{escape(get_formatted_hours(shop.shop_id))}</span>'
                f'<span class="dl-card__walk">{shop.walking_minutes:.0f} min walk</span></div>'
                f'<div class="dl-card__meta" style="color:var(--stale)">Not ranked — last seen over 14 days ago</div></div>'
                for shop in stale_shop_objs
            )
            st.markdown(f'<div class="dl-stale-list">{cards}</div>', unsafe_allow_html=True)

        st.caption("Sponsors never affect ranking. Some nutrition data from "
                   "[Open Food Facts](https://world.openfoodfacts.org) (ODbL), where our photo didn't show it.")

    with map_tab:
        # For map rankings and markers, each shop has one primary featured lunch
        all_ranked = [primary] + other_shops if primary else []
        for l in all_ranked:
            st.session_state[f"why_{l.shop.shop_id}"] = l.why or ""
        map_shops = [s for s in shops if not open_now or is_shop_open(s.shop_id)]
        fmap = build_map(
            ranked_lunches=all_ranked,
            all_shops=map_shops,
            walking_limit_minutes=prefs.max_walking_minutes,
            open_now_only=open_now,
        )
        map_open_suffix = " open" if open_now else ""
        st.caption(f"{len(map_shops)} shops{map_open_suffix} shown on map")
        map_data = st_folium(
            fmap,
            width=900,
            height=500,
            returned_objects=["last_object_clicked", "last_object_clicked_tooltip", "last_object_clicked_popup"],
        )

        # Detect clicked shop on map
        clicked_shop_id = None
        if map_data:
            clicked_obj = map_data.get("last_object_clicked")
            clicked_tooltip = map_data.get("last_object_clicked_tooltip") or ""
            clicked_popup = map_data.get("last_object_clicked_popup") or ""
            if clicked_obj and isinstance(clicked_obj, dict):
                clat = clicked_obj.get("lat")
                clng = clicked_obj.get("lng")
                if clat is not None and clng is not None:
                    match = next(
                        (s for s in map_shops if abs(s.lat - clat) < 0.0003 and abs(s.lng - clng) < 0.0003),
                        None,
                    )
                    if match:
                        clicked_shop_id = match.shop_id
            if not clicked_shop_id and clicked_tooltip:
                match = next((s for s in map_shops if s.name.lower() in clicked_tooltip.lower()), None)
                if match:
                    clicked_shop_id = match.shop_id
            if not clicked_shop_id and clicked_popup:
                match = next((s for s in map_shops if s.name.lower() in str(clicked_popup).lower()), None)
                if match:
                    clicked_shop_id = match.shop_id

        if clicked_shop_id:
            st.session_state["map_selected_shop_id"] = clicked_shop_id
            selected_shop_id = clicked_shop_id
        else:
            selected_shop_id = st.session_state.get("map_selected_shop_id")

        if selected_shop_id and open_now and not is_shop_open(selected_shop_id):
            selected_shop_id = primary.shop.shop_id if primary else None
            st.session_state["map_selected_shop_id"] = selected_shop_id

        # Fallback to primary shop if nothing selected yet
        if not selected_shop_id and primary:
            selected_shop_id = primary.shop.shop_id
            st.session_state["map_selected_shop_id"] = selected_shop_id

        if selected_shop_id:
            sel_shop = next((s for s in map_shops if s.shop_id == selected_shop_id), None)
            sel_lunch = next((l for l in all_ranked if l.shop.shop_id == selected_shop_id), None)
            if sel_shop:
                with st.container(border=True):
                    mcol1, mcol2, mcol3 = st.columns([3, 2, 1])
                    with mcol1:
                        rank_prefix = ""
                        if sel_lunch:
                            sel_rank = next((i + 1 for i, l in enumerate(all_ranked) if l.shop.shop_id == selected_shop_id), 0)
                            rank_prefix = f"#{sel_rank} " if sel_rank > 0 else ""
                        st.markdown(
                            f"{logo_html(sel_shop)}<b>{rank_prefix}{sel_shop.name}</b>",
                            unsafe_allow_html=True,
                        )
                        sel_is_open = is_shop_open(sel_shop.shop_id)
                        sel_badge_cls = "dl-badge--open" if sel_is_open else "dl-badge--closed"
                        sel_status_label = "Open Now" if sel_is_open else "Closed"
                        sel_hours = get_formatted_hours(sel_shop.shop_id)
                        sel_hours_html = f' <span class="dl-card__hours">{escape(sel_hours)}</span>' if sel_hours else ""
                        st.markdown(
                            f'<div style="margin: var(--space-1) 0;"><span class="dl-badge {sel_badge_cls}">{sel_status_label}</span>{sel_hours_html}</div>',
                            unsafe_allow_html=True,
                        )
                        st.caption(f"{sel_shop.walking_minutes:.0f} min walk")
                        if sel_lunch:
                            st.markdown(f"{sel_lunch.main.name} + {sel_lunch.snack.name} + {sel_lunch.drink.name}")
                        else:
                            st.caption("Outside your active filters")
                    with mcol2:
                        if sel_lunch:
                            st.markdown(f"### £{sel_lunch.price_gbp:.2f}")
                            deal_str = "Meal deal" if sel_lunch.used_deal else "Bought separately"
                            st.caption(f"✅ {deal_str}")
                    with mcol3:
                        if st.button("View basket →", key=f"map_see_basket_{sel_shop.shop_id}"):
                            st.session_state["detail_shop_id"] = sel_shop.shop_id
                            if sel_lunch:
                                st.session_state[f"why_{sel_shop.shop_id}"] = sel_lunch.why or ""
                            st.session_state["screen"] = "detail"
                            st.rerun()


# ---------------------------------------------------------------------------
# Screen 2: Shop detail
# ---------------------------------------------------------------------------

def _heading(level: int, text: str, prefix_html: str = "") -> None:
    """
    Screen (1) / section (2) heading in the h1/h2 type tokens. A div with role=heading,
    because Streamlit's own h1/h2 styles override the .dl-type-* sizes on real h tags.
    """
    type_class = {1: "dl-type-h1", 2: "dl-type-h2"}[level]
    st.markdown(
        f'<div class="{type_class}" role="heading" aria-level="{level}" '
        f'style="margin:var(--space-4) 0 var(--space-2)">{prefix_html}{escape(text)}</div>',
        unsafe_allow_html=True,
    )


def _bold_html(text: str) -> str:
    """'**x**' → '<strong>x</strong>' for markdown copy reused inside HTML blocks."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(text, quote=False))


def _allergy_box_html() -> str:
    """The full allergy warning as .dl-box--allergy (never dismissable, serious mode)."""
    return f'<div class="dl-box dl-box--allergy">{_bold_html(ALLERGY_WARNING)}</div>'


def _item_allergen_html(item) -> str:
    """Allergen line: values without unchecked placeholder or source tag."""
    if not item.allergens:
        return ""
    allergens = escape(", ".join(item.allergens))
    return f'<div class="dl-allergen-line">Allergens: {allergens}</div>'


def _price_html(item, prefs: Preferences | None = None) -> str:
    if item.price_gbp is None:
        return '<span class="dl-item__dealonly">meal deal only</span>'
    price = effective_price(item, prefs) if prefs is not None else item.price_gbp
    card = (' <span class="dl-badge dl-badge--credits">card price</span>'
            if price is not None and price < item.price_gbp else "")
    return f'<span class="dl-item__price">£{price:.2f}</span>{card}'


def _item_info_html(item, prefs: Preferences | None = None) -> str:
    """Name, price, tags, allergens, nutrition and freshness under a shop-page picker."""
    tags = []
    if item.temperature == "hot":
        tags.append('<span class="dl-item__meta">🔥 hot</span>')
    if item.meal_deal_eligible is False:
        tags.append('<span class="dl-item__meta">not in deal</span>')
    if item.status == "pending":
        tags.append('<span class="dl-badge dl-badge--unverified">Unverified</span>')
    return (
        f'<div class="dl-item">'
        f'<div class="dl-item__name">{escape(item.name)}</div>'
        f'<div class="dl-item__row">{_price_html(item, prefs)}{"".join(tags)}</div>'
        f'{_item_allergen_html(item)}'
        f'<div class="dl-item__meta">{escape(_item_nutrition(item))}</div>'
        f'<div class="dl-item__row">{_freshness_badge(str(item.last_seen))}</div>'
        f'</div>'
    )


def _deal_compare_html(deal, deal_eligible: bool, sep_price, is_deal_better: bool,
                       price: float | None = None) -> str:
    """DealComparison: meal deal vs bought separately; the winner has the border AND the words."""
    price = deal.price_gbp if (price is None and deal is not None) else price
    card_note = (f'<div class="dl-compare__note">{escape(deal.loyalty_scheme or "Card")} price '
                 f'(£{deal.price_gbp:.2f} without)</div>'
                 if deal is not None and price < deal.price_gbp else "")
    if deal is None:
        deal_body = '<div class="dl-compare__na">No deal at this shop</div>'
    elif not deal_eligible:
        deal_body = (f'<div class="dl-compare__na">Not available</div>'
                     f'<div class="dl-compare__note">£{price:.2f} deal — an item you picked '
                     f"isn't in the meal deal.</div>")
    else:
        note = ""
        if is_deal_better and sep_price is not None:
            note = (f'<div class="dl-compare__note dl-compare__note--win">'
                    f'✓ Best option — saves £{sep_price - price:.2f}</div>')
        elif is_deal_better:
            note = '<div class="dl-compare__note dl-compare__note--win">✓ Best option</div>'
        deal_body = f'<div class="dl-compare__price">£{price:.2f}</div>{card_note}{note}'

    sep_win = not is_deal_better and sep_price is not None
    if sep_price is None:
        sep_body = ('<div class="dl-compare__na">Not available</div>'
                    '<div class="dl-compare__note">An item you picked is only priced as part of the meal deal.</div>')
    else:
        sep_body = f'<div class="dl-compare__price">£{sep_price:.2f}</div>'
        if sep_win:
            sep_body += '<div class="dl-compare__note dl-compare__note--win">✓ Best option</div>'

    deal_cls = "dl-compare__opt is-winner" if is_deal_better else "dl-compare__opt"
    sep_cls = "dl-compare__opt is-winner" if sep_win else "dl-compare__opt"
    return (
        f'<div class="dl-compare">'
        f'<div class="{deal_cls}"><div class="dl-compare__label">Meal deal price</div>{deal_body}</div>'
        f'<div class="{sep_cls}"><div class="dl-compare__label">Bought separately</div>{sep_body}</div>'
        f'</div>'
    )


def screen_detail(prefs: Preferences | None = None):
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
    _heading(1, shop.name, prefix_html=logo_html(shop, size=40))
    # Pull the why from the last ranked result for this shop if available
    why_text = st.session_state.get(f"why_{shop_id}", "")
    is_open = is_shop_open(shop_id)
    badge_cls = "dl-badge--open" if is_open else "dl-badge--closed"
    status_label = "Open Now" if is_open else "Closed"
    hours_str = get_formatted_hours(shop_id)
    if hours_str:
        st.markdown(
            f'<div style="margin: var(--space-1) 0 var(--space-2);"><span class="dl-badge {badge_cls}">{status_label}</span> <span class="dl-card__hours">{escape(hours_str)}</span></div>',
            unsafe_allow_html=True,
        )
    sub = f"{shop.walking_minutes:.0f} min walk from campus"
    if why_text:
        sub += f" · {why_text}"
    st.caption(sub)
    if any(i.shop_id == shop_id and i.source_image == "fallback.jpg" for i in all_items):
        st.markdown('<div class="dl-box dl-box--sample"><strong>Sample data</strong> — we haven\'t '
                    'photographed this shop yet, so the products and prices below are placeholders, '
                    'not real readings.</div>', unsafe_allow_html=True)

    # Items for this shop
    shop_items = [i for i in all_items if i.shop_id == shop_id and i.status in ("approved", "pending")]
    mains  = [i for i in shop_items if i.category == "main"]
    snacks = [i for i in shop_items if i.category == "snack"]
    drinks = [i for i in shop_items if i.category == "drink"]
    shop_deals = [d for d in deals if d.shop_id == shop_id]

    if not mains or not snacks or not drinks:
        st.info("Not enough items to build a full basket for this shop yet.")
        return

    # The pickers start at index 0 and "Reset to best basket" returns there, so put the
    # shop's best lunch first (otherwise index 0 could be an unbuyable combination, e.g. a
    # main outside the deal with a deal-only drink)
    # Show everything at this shop (no diet/allergy filtering), but price it with the
    # shopper's own loyalty cards
    cards = ("has_clubcard", "has_nectar", "has_lidl_plus", "has_sparks", "has_mywaitrose", "has_club_pret")
    price_prefs = Preferences(**{c: getattr(prefs, c) for c in cards}) if prefs is not None else Preferences()
    best = best_lunch_for_shop(shop, hard_filter(shop_items, Preferences()), shop_deals, price_prefs)
    if best is not None:
        for options, pick in ((mains, best.main), (snacks, best.snack), (drinks, best.drink)):
            options.sort(key=lambda i, pick=pick: i.item_id != pick.item_id)

    key_prefix = f"detail_{shop_id}"

    # Apply any pending swaps / resets BEFORE display
    for cat in ("main", "snack", "drink"):
        pending = f"{key_prefix}_{cat}_pending"
        if pending in st.session_state:
            st.session_state[f"{key_prefix}_{cat}"] = st.session_state.pop(pending)

    _heading(2, "Build your basket")
    picked = {}
    for col, (cat, label, options) in zip(
        st.columns(3),
        (("main", "Main", mains), ("snack", "Snack", snacks), ("drink", "Drink", drinks)),
    ):
        with col:
            st.markdown(f'<div class="dl-eyebrow">{label}</div>', unsafe_allow_html=True)
            idx = st.session_state.get(f"{key_prefix}_{cat}", 0)
            if idx >= len(options):
                idx = 0
            st.session_state[f"{key_prefix}_{cat}"] = idx
            picked[cat] = (idx, options[idx])
            st.markdown(_item_info_html(options[idx], price_prefs), unsafe_allow_html=True)
    (main_idx, main), (snack_idx, snack), (drink_idx, drink) = picked["main"], picked["snack"], picked["drink"]

    # Reset button
    if (main_idx, snack_idx, drink_idx) != (0, 0, 0):
        if st.button("Reset to best basket"):
            for cat in ("main", "snack", "drink"):
                st.session_state[f"{key_prefix}_{cat}_pending"] = 0
            st.rerun()

    # Pricing comparison
    sep_price = _separate_total([main, snack, drink], price_prefs)   # None = a deal-only item is picked
    deal_eligible = (
        main.meal_deal_eligible is not False
        and snack.meal_deal_eligible is not False
        and drink.meal_deal_eligible is not False
    )
    deal = shop_deal(shop_deals, shop_id)
    shown_deal_price = deal_price(deal, price_prefs) if deal else None
    is_deal_better = shown_deal_price is not None and deal_eligible and (sep_price is None or shown_deal_price < sep_price)

    _heading(2, "Meal deal or separate?")
    st.markdown(_deal_compare_html(deal, deal_eligible, sep_price, is_deal_better, shown_deal_price), unsafe_allow_html=True)

    st.divider()

    # Full catalogue table
    _heading(2, "Everything we've seen here")
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
        tags = [item.category]
        if item.temperature == "hot":
            tags.append("🔥 hot")
        if item.meal_deal_eligible is False:
            tags.append("not in deal")
        unverified = (' <span class="dl-badge dl-badge--unverified">Unverified</span>'
                      if item.status == "pending" else "")

        cat = item.category
        options = {"main": mains, "snack": snacks, "drink": drinks}[cat]
        try:
            idx = options.index(item)
        except ValueError:
            idx = None
        current_key = f"{key_prefix}_{cat}"
        in_basket = (idx is not None and st.session_state.get(current_key, 0) == idx)

        with st.container(key=f"dl_shelf_row_{item.item_id}"):
            info_col, action_col = st.columns([3, 1], vertical_alignment="center")
            with info_col:
                allergen_html = _item_allergen_html(item)
                st.markdown(
                    f'<div class="dl-row">'
                    f'<div class="dl-row__top"><strong class="dl-row__name">{escape(item.name)}</strong>{unverified} · {_price_html(item)}</div>'
                    f'<div class="dl-row__tags">{" · ".join(tags)}</div>'
                    f'{allergen_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with action_col:
                st.markdown(
                    f'<div class="dl-row__actions">{_freshness_badge(str(item.last_seen))}</div>',
                    unsafe_allow_html=True,
                )
                if in_basket:
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
                    st.caption(entry["notes"])

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
    _heading(1, "Add photos")
    st.info(
        "Pick the shop and what's in the photo, then upload one or many photos. "
        "One photo can cover a whole shelf — we'll pick out every product. "
        "Credits are paid once your photo is approved."
    )

    user_id = _ensure_user()
    if not user_id:
        st.info("Enter your username in the sidebar to earn credits.")

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
            st.info(problem)

    # ── Shop + photo type ───────────────────────────────────────────────────
    if active_task:
        st.markdown(
            f'<div class="dl-card dl-card--active">'
            f'<div class="dl-card__row"><span class="dl-card__title">Task: {escape(active_task["item_name"])}</span>'
            f'<span class="dl-badge dl-badge--credits">+{active_task["bonus_credits"]} credits once approved</span></div>'
            f'<div class="dl-card__muted">{escape(shops_by_id.get(active_task["shop_id"], active_task["shop_id"]))}</div>'
            f'<div class="dl-card__text">{escape(active_task["ask"])}</div></div>',
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
        _heading(2, "What we found")
        st.caption("Check each product, fix anything wrong, untick anything that isn't right.")
        edited_items, edited_deals, banners = _render_batch(batch, nonce)
        n_ticked = sum(int(f["include"].sum()) for f in edited_items.values()) + \
                   sum(int(f["include"].sum()) for f in edited_deals.values())
        submit_label = f"Submit {n_ticked} for review"
        if active_task:
            submit_label += f" — complete task (+{active_task['bonus_credits']} credits once approved)"
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
    _heading(2, "Tasks")
    st.caption("We need a closer photo of these products. Bonus credits for each, once approved.")

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

            state = " dl-card--done" if is_done else (" dl-card--active" if is_active else "")

            with cols[i % 3]:
                st.markdown(
                    f'<div class="dl-card{state}">'
                    f'<div class="dl-card__row"><span class="dl-card__title">{escape(task["item_name"])}</span>'
                    f'<span class="dl-badge dl-badge--credits">+{task["bonus_credits"]} credits once approved</span></div>'
                    f'<div class="dl-card__muted">{escape(shop_display)}</div>'
                    f'<div class="dl-card__muted">Needed: {escape(task["needed"])}</div>'
                    f'<div class="dl-card__text">{escape(task["ask"])}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if is_done:
                    st.markdown('<span class="dl-done">Done ✓</span>', unsafe_allow_html=True)
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
    _heading(1, "My credits")
    user_id = _ensure_user()
    if not user_id:
        st.info("Enter your username in the sidebar to see your credits.")
        return

    conn = _conn()
    handle = st.session_state.get("username", "")
    balance = get_user_credit_balance(conn, user_id)
    pending_est = ledger.get_pending_credits(conn, user_id)

    st.markdown(f"Hello, **{handle}**")

    # Earned credits are hype (sticker); pending ones are never shown as earned
    st.markdown(
        f'<div class="dl-tiles">'
        f'<div class="dl-tile dl-tile--earned"><div class="dl-tile__label">Ready to spend</div>'
        f'<div class="dl-tile__value">{balance}</div><div class="dl-tile__note">credits</div></div>'
        f'<div class="dl-tile dl-tile--pending"><div class="dl-tile__label">Awaiting review</div>'
        f'<div class="dl-tile__value">{pending_est}</div>'
        f'<div class="dl-tile__note">estimate · not earned yet — paid once approved</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # Rewards — kept visually separate from rankings
    _heading(2, "Rewards from sponsors")
    rewards = conn.execute("SELECT * FROM rewards").fetchall()
    if rewards:
        for r in rewards:
            rc1, rc2 = st.columns([3, 1])
            with rc1:
                st.markdown(
                    f'<div class="dl-card__title">{escape(r["title"])}</div>'
                    f'<div class="dl-card__muted">{escape(r["sponsor"])}</div>',
                    unsafe_allow_html=True,
                )
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
    _heading(2, "History")
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

        # .dl-status--<type> colours; the word always carries the meaning too
        STATUS_LABELS = {
            "earn":     "Approved",
            "spend":    "Redeemed",
            "reversal": "Not accepted",
        }

        hdr1, hdr2, hdr3 = st.columns([3, 2, 1])
        hdr1.caption("**Shop**")
        hdr2.caption("**Status**")
        hdr3.caption("**Credits**")

        for event in history:
            kind = event["type"] if event["type"] in STATUS_LABELS else "other"
            label = STATUS_LABELS.get(event["type"], event["type"])
            shop_name = _ref_to_shop(event["ref_id"]) if event.get("ref_id") else "—"
            sign = "+" if event["credits"] > 0 else ""

            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(shop_name)
            c2.markdown(f'<span class="dl-status dl-status--{kind}">{escape(label)}</span>',
                        unsafe_allow_html=True)
            c3.markdown(f'<span class="dl-item__price">{sign}{event["credits"]}</span>',
                        unsafe_allow_html=True)


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
    """One pending record as HTML: name + price, then a serious-mode allergen line."""
    if row["_type"] == "deal":
        card = f" · card £{row['loyalty_price_gbp']:.2f}" if row.get("loyalty_price_gbp") else ""
        return (f'<div class="dl-record"><strong>{escape(row.get("name") or "Meal Deal")}</strong> (deal sign) · '
                f'<span class="dl-item__price">£{row.get("price_gbp", 0):.2f}</span>{card}</div>')
    allergens = json.loads(row.get("allergens") or "[]")
    flag = ' <span class="dl-badge dl-badge--unverified">Unclear read</span>' if row.get("needs_review") else ""
    price = ('<span class="dl-item__dealonly">meal deal only</span>' if row.get("price_gbp") is None
             else f'<span class="dl-item__price">£{row["price_gbp"]:.2f}</span>')
    allergen_text = f"Allergens: {escape(', '.join(allergens))}" if allergens else "Allergens not checked"
    return (
        f'<div class="dl-record"><strong>{escape(row.get("name") or "")}</strong>{flag}'
        f'<div class="dl-record__meta">{escape(row.get("category") or "")} · {price}</div>'
        f'<div class="dl-allergen-line">{allergen_text}</div></div>'
    )


def screen_review():
    _heading(1, "Review queue")
    if not is_admin():
        st.info("Team only. Unlock admin mode under **Team** at the bottom of the sidebar.")
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
                    f'<div class="dl-card__title">{escape(shops_map.get(first["shop_id"], first["shop_id"]))}'
                    f' · {len(rows)} from this photo</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"Uploaded by {first.get('submitted_by') or 'seed walk'} · {first.get('last_seen', '')} · `{photo}`"
                )
                for r in rows:
                    line_col, ap_col, rj_col = st.columns([6, 1, 1])
                    line_col.markdown(_record_line(r), unsafe_allow_html=True)
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

    # Direct navigation from URL query param (e.g. from map popup "View basket →" link)
    shop_param = st.query_params.get("shop") or st.query_params.get("detail_shop_id")
    screen_param = st.query_params.get("screen")
    if shop_param:
        for k in ("shop", "detail_shop_id", "screen"):
            if k in st.query_params:
                del st.query_params[k]
        st.session_state["detail_shop_id"] = shop_param
        st.session_state["screen"] = "detail"
    elif screen_param:
        if "screen" in st.query_params:
            del st.query_params["screen"]
        if screen_param in ("find", "detail", "credits", "review", "demo"):
            st.session_state["screen"] = screen_param

    prefs = render_sidebar()
    render_admin_sidebar()

    if "screen" not in st.session_state:
        st.session_state["screen"] = "find"

    # Review queue only appears in the nav once admin mode is unlocked
    screens = {**SCREENS, **ADMIN_SCREENS} if is_admin() else SCREENS

    # Top nav, with the "?" tour button as a narrow last column (top-right corner)
    with st.container(key="dl_nav"):   # compact single row on phones (design/components.css)
        nav_cols = st.columns([1] * len(screens) + [0.25])
    # The shop page belongs to Find; the active screen's button is the primary one
    current = {"detail": "find"}.get(st.session_state["screen"], st.session_state["screen"])
    for col, (label, key) in zip(nav_cols, screens.items()):
        with col:
            if st.button(label, use_container_width=True, type="primary" if key == current else "secondary"):
                st.session_state["screen"] = key
                st.rerun()
    with nav_cols[-1]:
        if st.button("?", key="open_demo", help="Take a live tour of the site", use_container_width=True,
                     type="primary" if current == "demo" else "secondary"):
            st.session_state["demo_step"] = 0
            st.session_state["screen"] = "demo"
            st.rerun()

    st.divider()

    screen = st.session_state["screen"]

    if screen == "find":
        screen_find(prefs)
    elif screen == "detail":
        screen_detail(prefs)
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
