"""
Live tour of the site, opened from the "?" button in the top nav.

Every step renders the real components (results cards, map, pricing) using
hard-coded demo Preferences, so the user's own sidebar settings are never read
or changed. No Claude calls — the tour is instant.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st
from streamlit_folium import st_folium

from map_view import build_map
from models import Preferences
from optimiser import get_results, shop_deal
from shop_images import logo_html


DEMO_PREFS = Preferences(
    sort="deeel",
    temperature_pref="any",
    max_price_gbp=6.0,
    max_walking_minutes=10.0,
    has_clubcard=True,
    has_nectar=True,
    has_lidl_plus=True,
    has_sparks=True,
    has_mywaitrose=True,
    has_club_pret=True,
)

_STEPS = [
    "Welcome",
    "Your preferences",
    "Results",
    "Map view",
    "Filters in action",
    "Meal deal vs separate",
    "Add a photo & credits",
    "You're ready",
]


def _chip(text: str) -> str:
    """A selected preference, styled as an active DietChip (.dl-chip--diet.is-on)."""
    return (f'<span class="dl-chip dl-chip--diet is-on" '
            f'style="margin:0 var(--space-2) var(--space-2) 0">✓ {text}</span>')


# Navigation uses on_click callbacks: they update state before the next run,
# so no st.rerun() is needed and no stale buttons linger from the previous step.
def _go(step: int) -> None:
    st.session_state["demo_step"] = step


def _exit(to: str = "find") -> None:
    st.session_state.pop("demo_step", None)
    st.session_state["screen"] = to


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _step_welcome(data, render_card) -> None:
    st.markdown("### Find the best lunch near UCL")
    st.markdown(
        "Deeelicious ranks the shops around UCL Bloomsbury and builds the best "
        "**main + snack + drink** at each one, checking whether the meal deal or "
        "buying separately is cheaper."
    )
    with st.container(border=True):
        st.markdown("**Where the data comes from**")
        st.caption(
            "Prices, allergens and nutrition are read from in-store photos of shelf "
            "labels — taken on our seed walk and by students like you. No scraping."
        )
    shops = data[0]
    st.markdown(" ".join(logo_html(s, size=32) for s in shops), unsafe_allow_html=True)
    st.caption(f"{len(shops)} shops covered right now. This tour uses live data.")


def _step_preferences(data, render_card) -> None:
    st.markdown("### Tell us what you want")
    st.markdown(
        "Everything is set from the sidebar on the left: allergens, diet, meat, "
        "nutrition, budget, walking distance, hot or cold, loyalty cards and sort order."
    )
    st.markdown("For this tour we'll use:")
    p = DEMO_PREFS
    st.markdown(
        _chip(f"Max £{p.max_price_gbp:.2f}")
        + _chip(f"{p.max_walking_minutes:.0f} min walk")
        + _chip(f"{p.temperature_pref.title()} temperature")
        + _chip("Sort by Deeel score"),
        unsafe_allow_html=True,
    )
    st.caption("Your own sidebar settings aren't touched by the tour.")


def _step_results(data, render_card) -> None:
    shops, items, deals = data
    primary, alternatives, other_shops = get_results(shops, items, deals, DEMO_PREFS)
    st.markdown("### Results in three sections")
    if primary is None:
        st.info("No results for the demo preferences with the current data.")
        return
    st.caption("Section A — your single best option")
    render_card(primary, rank=1, prefs=DEMO_PREFS, featured=True, key_prefix="demo_")
    if alternatives:
        st.caption(f"Section B — other mains at {primary.shop.name}")
        for i, alt in enumerate(alternatives, start=2):
            render_card(alt, rank=i, prefs=DEMO_PREFS, key_prefix="demo_", show_rank=False)
    if other_shops:
        st.caption("Section C — the best lunch at other nearby shops")
        for i, lunch in enumerate(other_shops, start=len(alternatives) + 2):
            render_card(lunch, rank=i, prefs=DEMO_PREFS, key_prefix="demo_")
    st.info(
        "Each combination gets a **Deeel score** out of 100: value (30), fillingness (25), "
        "ingredient quality (25), nutrition balance (10) and deal saving (10). "
        "Tap **Deeel score** on any card for the breakdown."
    )
    st.caption("Sponsors never affect ranking.")


def _step_map(data, render_card) -> None:
    shops, items, deals = data
    primary, alternatives, other_shops = get_results(shops, items, deals, DEMO_PREFS)
    st.markdown("### See it on a map")
    st.markdown(
        "The **Map view** tab shows the same results. Markers display each shop's logo "
        "with a star badge on the #1 pick, grey for shops outside your filters, and the "
        "dashed circle is your walking limit."
    )
    ranked = [primary] + other_shops if primary else []
    fmap = build_map(ranked, shops, walking_limit_minutes=DEMO_PREFS.max_walking_minutes)
    st_folium(fmap, width=900, height=420, returned_objects=[], key="demo_map")


def _summary(lunch) -> str:
    if lunch is None:
        return "No match nearby"
    return (
        f"{logo_html(lunch.shop, size=22)}<b>{lunch.shop.name}</b> — "
        f"{lunch.main.name} + {lunch.snack.name} + {lunch.drink.name} · "
        f"<b>£{lunch.price_gbp:.2f}</b>"
    )


def _step_filters(data, render_card) -> None:
    shops, items, deals = data
    st.markdown("### Filters change the answer")
    scenarios = [
        ("No extra filters", DEMO_PREFS),
        ("Chicken main, at least 30 g protein for the meal",
         DEMO_PREFS.model_copy(update={"meats_allowed": ["chicken"], "min_protein_g": 30.0})),
        ("Vegetarian main", DEMO_PREFS.model_copy(update={"diet_flags": ["vegetarian"]})),
    ]
    for label, prefs in scenarios:
        primary, _, _ = get_results(shops, items, deals, prefs)
        with st.container(border=True):
            st.caption(label)
            st.markdown(_summary(primary), unsafe_allow_html=True)


def _step_deal(data, render_card) -> None:
    shops, items, deals = data
    primary, _, _ = get_results(shops, items, deals, DEMO_PREFS)
    st.markdown("### Meal deal or separate?")
    if primary is None:
        st.info("No results for the demo preferences with the current data.")
        return
    shop = primary.shop
    trio = (primary.main, primary.snack, primary.drink)
    sep_price = None if any(i.price_gbp is None for i in trio) else sum(i.price_gbp for i in trio)
    deal = shop_deal(deals, shop.shop_id)
    eligible = all(i.meal_deal_eligible for i in trio)
    st.markdown(
        f"{logo_html(shop)}At <b>{shop.name}</b>: {' + '.join(i.name for i in trio)}",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.caption("Meal deal price")
            if deal is None:
                st.markdown("**No deal at this shop**")
            elif not eligible:
                st.markdown(f"**£{deal.price_gbp:.2f}** — not available")
                st.caption("One of these items isn't in the meal deal.")
            else:
                st.markdown(f"**£{deal.price_gbp:.2f}**")
                if sep_price is None:
                    st.caption("✅ Best option — some items are only sold in the deal")
                elif deal.price_gbp < sep_price:
                    st.caption(f"✅ Best option — saves £{sep_price - deal.price_gbp:.2f}")
    with c2:
        with st.container(border=True):
            st.caption("Bought separately")
            st.markdown("**Not available**" if sep_price is None else f"**£{sep_price:.2f}**")
            if sep_price is not None and (deal is None or not eligible or deal.price_gbp >= sep_price):
                st.caption("✅ Best option")
    st.caption("Tap **See basket** on any result to swap items and watch the price update.")


def _step_photo(data, render_card) -> None:
    shops, items, deals = data
    st.markdown("### Add a photo, earn credits")
    st.markdown(
        "1. Pick the shop and photograph the shelf label.\n"
        "2. We read the price, allergens, meat and nutrition from the label.\n"
        "3. You check it and submit. Clear photos go live straight away as *unverified*."
    )
    example = next((i for i in items if i.category == "main" and i.status == "approved"), None)
    if example is not None:
        shop_name = next((s.name for s in shops if s.shop_id == example.shop_id), example.shop_id)
        with st.container(border=True):
            st.caption(f"Example — what we read from a label at {shop_name}")
            rows = [
                ("Item", example.name),
                ("Type", example.category),
                ("Price", "meal deal only" if example.price_gbp is None else f"£{example.price_gbp:.2f}"),
                ("Deal", "✅ eligible" if example.meal_deal_eligible else "Not in deal"),
                ("Allergens", (", ".join(example.allergens) or "none on label") + " · ⚠️ computer-read — check the pack"),
                ("Meat", "not on label" if example.meats is None else (", ".join(example.meats) or "none")),
            ]
            for label, val in rows:
                st.markdown(f"**{label}:** {val}")
    st.info("Credits are paid **only when your photo is approved**. Pending photos earn 0 until then.")
    st.caption("Spend credits on rewards under **My credits**.")


def _step_done(data, render_card) -> None:
    st.markdown("### You're ready")
    st.markdown(
        "Set your preferences in the sidebar and your best lunch appears instantly. "
        "Come back to this tour any time with the **?** button."
    )
    st.button("Try it yourself →", type="primary", key="demo_try", on_click=_exit)


_RENDERERS = [
    _step_welcome, _step_preferences, _step_results, _step_map,
    _step_filters, _step_deal, _step_photo, _step_done,
]


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

def screen_demo(load_data: Callable, render_card: Callable) -> None:
    """
    load_data   -> (shops, items, deals), the app's cached loader
    render_card -> app.render_result_card (passed in to avoid a circular import)
    """
    step = max(0, min(st.session_state.get("demo_step", 0), len(_STEPS) - 1))

    head, close = st.columns([5, 1])
    with head:
        st.markdown(f"## Tour · {_STEPS[step]}")
        st.caption(f"Step {step + 1} of {len(_STEPS)}")
    with close:
        st.button("Exit tour", key="demo_exit", use_container_width=True, on_click=_exit)
    st.progress((step + 1) / len(_STEPS))

    _RENDERERS[step](load_data(), render_card)

    st.divider()
    back, _, nxt = st.columns([1, 3, 1])
    with back:
        if step > 0:
            st.button("← Back", key="demo_back", use_container_width=True,
                      on_click=_go, args=(step - 1,))
    with nxt:
        if step < len(_STEPS) - 1:
            st.button("Next →", key="demo_next", type="primary", use_container_width=True,
                      on_click=_go, args=(step + 1,))
