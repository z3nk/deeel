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
from optimiser import WALK_SPEED_MPM

# UCL Main Quad, Gower Street
CAMPUS_LAT = 51.5246
CAMPUS_LNG = -0.1340

# Marker colours matching UI_BRIEF colour tokens
COLOUR_RANK1 = "#16A34A"   # green
COLOUR_RANK2 = "#EAB308"   # yellow
COLOUR_RANK3 = "#F97316"   # orange
COLOUR_GREY  = "#94A3B8"   # out of range / filtered


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
        color="#0F7B5F",
        weight=2,
        dash_array="6 4",
        fill=True,
        fill_color="#0F7B5F",
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
            popup_html = (
                f"<b>#{rank} {shop.name}</b><br>"
                f"{shop.walking_minutes:.0f} min walk<br>"
                f"{lunch.main.name} + {lunch.snack.name} + {lunch.drink.name}<br>"
                f"<b>£{lunch.price_gbp:.2f}</b> · {deal_label}"
            )
        else:
            colour = COLOUR_GREY
            popup_html = (
                f"<b>{shop.name}</b><br>"
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
            tooltip=shop.name,
        ).add_to(m)

        # Rank label on the marker
        if shop.shop_id in ranked_index:
            rank, _ = ranked_index[shop.shop_id]
            folium.Marker(
                location=[shop.lat, shop.lng],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:11px;font-weight:700;color:#fff;'
                         f'text-align:center;line-height:24px;">{rank}</div>',
                    icon_size=(24, 24),
                    icon_anchor=(12, 12),
                ),
            ).add_to(m)

    return m
