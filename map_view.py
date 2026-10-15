"""
Folium map helper for Screen 1 Map view tab.

build_map() returns a folium.Map ready to pass to st_folium().
- Campus origin: blue star marker
- Each ranked shop: circle marker coloured by rank
- Shops outside walking limit: grey marker
- Dashed circle = walking-limit radius
"""

from __future__ import annotations

import math

import folium

from models import Lunch, Shop
from optimiser import WALK_SPEED_MPM, is_sample
from theme import token, type_css
from shop_images import logo_html

# UCL Main Quad, Gower Street
CAMPUS_LAT = 51.5246
CAMPUS_LNG = -0.1340

# Marker colours from design/tokens.json. The map renders in its own iframe, so
# CSS variables don't reach it: resolved values via theme.token() instead.
COLOUR_RANK1 = token("rank-1")     # green
COLOUR_RANK2 = token("rank-2")     # yellow
COLOUR_RANK3 = token("rank-3")     # orange
COLOUR_GREY  = token("rank-out")   # out of range / filtered


def _rank_colour(rank: int) -> str:
    if rank == 1:
        return COLOUR_RANK1
    if rank == 2:
        return COLOUR_RANK2
    if rank >= 3:
        return COLOUR_RANK3
    return COLOUR_GREY


def _walking_radius_metres(walking_limit_minutes: float) -> float:
    return walking_limit_minutes * WALK_SPEED_MPM


def build_map(
    ranked_lunches: list[Lunch],
    all_shops: list[Shop],
    walking_limit_minutes: float = 10.0,
    campus_lat: float = CAMPUS_LAT,
    campus_lng: float = CAMPUS_LNG,
) -> folium.Map:
    """
    Build and return a Folium map for the Map view tab.

    Parameters
    ----------
    ranked_lunches  : ordered list of Lunch objects (primary first)
    all_shops       : full shop list (to show grey markers for filtered shops)
    walking_limit_minutes : current sidebar walking-limit value
    """
    m = folium.Map(
        location=[campus_lat, campus_lng],
        zoom_start=15,
        tiles="OpenStreetMap",
    )

    # ── Walking-limit radius circle ────────────────────────────────────────
    radius_m = _walking_radius_metres(walking_limit_minutes)
    folium.Circle(
        location=[campus_lat, campus_lng],
        radius=radius_m,
        color=token("primary"),
        weight=2,
        dash_array="6 4",
        fill=True,
        fill_color=token("primary"),
        fill_opacity=0.05,
        tooltip=f"{int(walking_limit_minutes)} min walk radius",
    ).add_to(m)

    # ── Campus origin marker ───────────────────────────────────────────────
    folium.Marker(
        location=[campus_lat, campus_lng],
        tooltip="You are here (UCL Main Quad)",
        icon=folium.Icon(color="blue", icon="star", prefix="fa"),
    ).add_to(m)

    # Build lookup: shop_id → (rank, lunch)
    ranked_index: dict[str, tuple[int, Lunch]] = {
        lunch.shop.shop_id: (i + 1, lunch)
        for i, lunch in enumerate(ranked_lunches)
    }

    # ── Shop markers ───────────────────────────────────────────────────────
    for shop in all_shops:
        if shop.lat == 0 and shop.lng == 0:
            continue  # skip shops with no coordinates

        if shop.shop_id in ranked_index:
            rank, lunch = ranked_index[shop.shop_id]
            colour = _rank_colour(rank)
            deal_label = "Meal deal" if lunch.used_deal else "Separate"
            sample_note = "<br><i>Sample data — not photographed yet</i>" if is_sample(lunch) else ""
            popup_html = (
                f"{logo_html(shop, size=22, standalone=True)}<b>#{rank} {shop.name}</b><br>"
                f"{shop.walking_minutes:.0f} min walk<br>"
                f"{lunch.main.name} + {lunch.snack.name} + {lunch.drink.name}<br>"
                f"<b>£{lunch.price_gbp:.2f}</b> · {deal_label}{sample_note}"
            )
        else:
            colour = COLOUR_GREY
            popup_html = (
                f"{logo_html(shop, size=22, standalone=True)}<b>{shop.name}</b><br>"
                f"{shop.walking_minutes:.0f} min walk<br>"
                f"<i>Outside your filters</i>"
            )

        folium.CircleMarker(
            location=[shop.lat, shop.lng],
            radius=12,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.85,
            weight=2,
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=shop.name + (" (sample data)" if shop.shop_id in ranked_index
                                 and is_sample(ranked_index[shop.shop_id][1]) else ""),
        ).add_to(m)

        # Rank label on the marker
        if shop.shop_id in ranked_index:
            rank, _ = ranked_index[shop.shop_id]
            folium.Marker(
                location=[shop.lat, shop.lng],
                icon=folium.DivIcon(
                    html=f'<div style="{type_css("caption")};font-weight:700;color:{token("rank-ink")};'
                         f'text-align:center;line-height:24px;">{rank}</div>',
                    icon_size=(24, 24),
                    icon_anchor=(12, 12),
                ),
            ).add_to(m)

    return m
