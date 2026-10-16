"""
Folium map helper for Screen 1 Map view tab.

build_map() returns a folium.Map ready to pass to st_folium().
- Campus origin: blue star marker
- Each shop: custom pin with shop logo (single Marker & DivIcon)
- Top-ranked (#1) shop: prominent star badge overlay
- Shops outside walking limit: grey marker
- Dashed circle = walking-limit radius
- Base tiles: CartoDB Positron light tiles
"""

from __future__ import annotations

import os
from datetime import datetime
import folium
import streamlit as st
from dotenv import load_dotenv

from models import Lunch, Shop
from optimiser import WALK_SPEED_MPM, is_sample
from theme import token, type_css
from shop_images import logo_html, logo_data_uri, _BADGES
from hours import is_shop_open, get_formatted_hours

load_dotenv()

# UCL Main Quad, Gower Street
CAMPUS_LAT = 51.5246
CAMPUS_LNG = -0.1340

# Marker colours from design/tokens.json. The map renders in its own iframe, so
# CSS variables don't reach it: resolved values via theme.token() instead.
COLOUR_RANK1 = token("rank-1")     # green
COLOUR_RANK2 = token("rank-2")     # yellow
COLOUR_RANK3 = token("rank-3")     # orange
COLOUR_GREY  = token("rank-out")   # out of range / filtered

OSM_TILES_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_TILES_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
CARTO_VOYAGER_URL = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
CARTO_POSITRON_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
CARTO_TILES_URL = CARTO_VOYAGER_URL
CARTO_TILES_ATTR = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
)


def get_carto_tiles_url() -> str:
    """
    Resolve the CARTO basemap tile URL.

    Reads CARTO_API_KEY or CARTO_KEY from environment (.env) or Streamlit secrets.
    CARTO basemaps requires '?key=<token>' query parameter.
    """
    api_key = os.environ.get("CARTO_API_KEY") or os.environ.get("CARTO_KEY")
    if not api_key:
        try:
            api_key = (
                st.secrets.get("CARTO_API_KEY")
                or st.secrets.get("CARTO_KEY")
                or st.secrets.get("carto_api_key")
                or st.secrets.get("carto_key")
            )
        except Exception:
            pass

    custom_url = os.environ.get("CARTO_TILES_URL")
    if not custom_url:
        try:
            custom_url = st.secrets.get("CARTO_TILES_URL")
        except Exception:
            pass
    base_url = (custom_url or CARTO_TILES_URL).strip()

    if api_key and api_key.strip():
        clean_key = api_key.strip()
        delim = "&" if "?" in base_url else "?"
        return f"{base_url}{delim}key={clean_key}"
    if custom_url:
        return base_url
    # CARTO's basemap shows an "API KEY REQUIRED" watermark without a key: use OpenStreetMap
    return OSM_TILES_URL


def _rank_colour(rank: int) -> str:
    if rank == 1:
        return COLOUR_RANK1
    if rank == 2:
        return COLOUR_RANK2
    if rank >= 3:
        return COLOUR_RANK3
    return COLOUR_GREY


def _brand_colours(chain: str) -> tuple[str, str]:
    """(pin fill, rank-number ink) in the shop's brand colour, from design/tokens.json."""
    if chain in _BADGES:
        return token(f"shop-{chain}"), token(_BADGES[chain][1])
    return token("primary"), token("on-primary")


def _walking_radius_metres(walking_limit_minutes: float) -> float:
    return walking_limit_minutes * WALK_SPEED_MPM


def _marker_icon_html(shop: Shop, rank: int | None = None) -> str:
    """Generate HTML for circular shop logo pin with star badge overlay for rank #1."""
    data_uri = logo_data_uri(shop.chain)
    is_rank1 = (rank == 1)

    t_surface = token("surface")
    t_radius_chip = token("radius-chip")
    t_accent_yellow = token("accent-yellow")
    t_text = token("text")

    if rank is not None:
        border_col, _ = _brand_colours(shop.chain)
        opacity = "1.0"
    else:
        border_col = COLOUR_GREY
        opacity = "0.7"

    star_badge = ""
    if is_rank1:
        star_badge = (
            f'<div style="position:absolute;top:-6px;right:-6px;width:18px;height:18px;'
            f'background:{t_accent_yellow};border:2px solid {t_surface};'
            f'border-radius:{t_radius_chip};display:flex;align-items:center;'
            f'justify-content:center;box-shadow:0 1px 3px rgba(31,35,40,0.3);z-index:10;">'
            f'<svg viewBox="0 0 24 24" width="11" height="11" fill="{t_text}">'
            f'<path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>'
            f'</svg></div>'
        )

    if data_uri:
        logo_inner = (
            f'<img src="{data_uri}" alt="{shop.name}" style="width:24px;height:24px;'
            f'object-fit:contain;display:block;pointer-events:none;">'
        )
    else:
        badge_text = _BADGES.get(shop.chain, (shop.name[:1].upper(), "text"))[0]
        logo_inner = (
            f'<span style="font-weight:700;{type_css("caption")};color:{border_col};'
            f'pointer-events:none;line-height:1;">{badge_text}</span>'
        )

    return (
        f'<div style="position:relative;width:36px;height:36px;background:{t_surface};'
        f'border:2.5px solid {border_col};border-radius:{t_radius_chip};'
        f'display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(31,35,40,0.22);'
        f'opacity:{opacity};cursor:pointer;box-sizing:border-box;">'
        f'{logo_inner}{star_badge}'
        f'</div>'
    )


def _campus_marker_icon_html() -> str:
    """Generate HTML for the UCL Main Quad origin marker in Deeelicious brand colours."""
    t_primary = token("primary")
    t_surface = token("surface")
    t_on_primary = token("on-primary")
    t_radius_chip = token("radius-chip")
    return (
        f'<div style="position:relative;width:34px;height:34px;background:{t_primary};'
        f'border:2.5px solid {t_surface};border-radius:{t_radius_chip};'
        f'display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(15,123,95,0.45);'
        f'cursor:pointer;box-sizing:border-box;" title="You are here (UCL Main Quad)">'
        f'<svg viewBox="0 0 24 24" width="18" height="18" fill="{t_on_primary}">'
        f'<path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z"/>'
        f'</svg>'
        f'</div>'
    )


def build_map(
    ranked_lunches: list[Lunch],
    all_shops: list[Shop],
    walking_limit_minutes: float = 10.0,
    campus_lat: float = CAMPUS_LAT,
    campus_lng: float = CAMPUS_LNG,
    open_now_only: bool = False,
    now: datetime | None = None,
) -> folium.Map:
    """
    Build and return a Folium map for the Map view tab.

    Parameters
    ----------
    ranked_lunches  : ordered list of Lunch objects (primary first)
    all_shops       : full shop list (to show grey markers for filtered shops)
    walking_limit_minutes : current sidebar walking-limit value
    open_now_only   : if True, exclude closed supermarkets from map markers
    now             : datetime for hours evaluation (defaults to local now)
    """
    if open_now_only:
        all_shops = [s for s in all_shops if is_shop_open(s.shop_id, now)]
        ranked_lunches = [l for l in ranked_lunches if is_shop_open(l.shop.shop_id, now)]

    tiles_url = get_carto_tiles_url()
    is_osm = (tiles_url == OSM_TILES_URL)

    m = folium.Map(
        location=[campus_lat, campus_lng],
        zoom_start=15,
        tiles=tiles_url,
        attr=OSM_TILES_ATTR if is_osm else CARTO_TILES_ATTR,
    )

    # ── Injected tokenized styling and cross-iframe navigation script ──
    t_bg = token("bg")
    t_surface = token("surface")
    t_border = token("border")
    t_hairline = token("border-width-hairline")
    t_radius_card = token("radius-card")
    t_radius_button = token("radius-button")
    t_radius_chip = token("radius-chip")
    t_space_1 = token("space-1")
    t_space_2 = token("space-2")
    t_space_3 = token("space-3")
    t_text = token("text")
    t_text_muted = token("text-muted")
    t_primary = token("primary")
    t_on_primary = token("on-primary")
    t_primary_tint = token("primary-tint")
    t_success_tint = token("success-tint")
    t_success_ink = token("success-ink")
    t_sample = token("sample")
    t_sample_tint = token("sample-tint")
    t_sample_outline = token("sample-outline")
    t_rank_ink = token("rank-ink")

    css_h3 = type_css("h3")
    css_small = type_css("small")
    css_body = type_css("body")
    css_caption = type_css("caption")
    css_label = type_css("label")
    css_price_sm = type_css("price-sm")

    tile_filter = (
        "mix-blend-mode: multiply; filter: grayscale(0.65) sepia(0.15) brightness(1.04) contrast(0.92);"
        if is_osm
        else "mix-blend-mode: multiply; filter: brightness(1.02) contrast(0.98);"
    )

    popup_header_html = (
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;700&display=swap">\n'
        '<style>\n'
        f'.leaflet-container {{\n'
        f'  background-color: {t_bg} !important;\n'
        f'  font-family: Figtree, system-ui, sans-serif !important;\n'
        f'}}\n'
        f'.leaflet-tile-pane {{\n'
        f'  {tile_filter}\n'
        f'}}\n'
        f'.leaflet-bar {{\n'
        f'  border-radius: {t_radius_button} !important;\n'
        f'  overflow: hidden !important;\n'
        f'  border: {t_hairline} solid {t_border} !important;\n'
        f'  box-shadow: 0 1px 4px rgba(31, 35, 40, 0.12) !important;\n'
        f'}}\n'
        f'.leaflet-bar a {{\n'
        f'  background-color: {t_surface} !important;\n'
        f'  color: {t_text} !important;\n'
        f'  border-bottom: {t_hairline} solid {t_border} !important;\n'
        f'  transition: background-color 0.15s ease, color 0.15s ease !important;\n'
        f'}}\n'
        f'.leaflet-bar a:hover {{\n'
        f'  background-color: {t_primary_tint} !important;\n'
        f'  color: {t_primary} !important;\n'
        f'}}\n'
        f'.leaflet-bar a:last-child {{\n'
        f'  border-bottom: none !important;\n'
        f'}}\n'
        f'.leaflet-control-attribution {{\n'
        f'  background: rgba(254, 249, 235, 0.85) !important;\n'
        f'  color: {t_text_muted} !important;\n'
        f'  {css_caption} !important;\n'
        f'  border-top-left-radius: 4px !important;\n'
        f'  padding: 2px 6px !important;\n'
        f'}}\n'
        f'.leaflet-control-attribution a {{\n'
        f'  color: {t_primary} !important;\n'
        f'}}\n'
        '.leaflet-div-icon { background: transparent !important; border: none !important; }\n'
        f'.leaflet-popup-content-wrapper {{\n'
        f'  background: {t_surface} !important;\n'
        f'  border-radius: {t_radius_card} !important;\n'
        f'  border: {t_hairline} solid {t_border} !important;\n'
        f'  box-shadow: 0 4px 16px rgba(31, 35, 40, 0.12) !important;\n'
        f'  padding: 0 !important;\n'
        f'}}\n'
        f'.leaflet-popup-content {{\n'
        f'  margin: {t_space_3} !important;\n'
        f'  line-height: 1.4 !important;\n'
        f'  color: {t_text} !important;\n'
        f'  font-family: Figtree, system-ui, sans-serif !important;\n'
        f'}}\n'
        f'.leaflet-popup-content a:hover {{\n'
        f'  opacity: 0.9 !important;\n'
        f'}}\n'
        f'.leaflet-popup-tip {{\n'
        f'  background: {t_surface} !important;\n'
        f'  box-shadow: 0 4px 16px rgba(31, 35, 40, 0.12) !important;\n'
        f'}}\n'
        f'.leaflet-container a.leaflet-popup-close-button {{\n'
        f'  color: {t_text_muted} !important;\n'
        f'  padding: 6px 8px 0 0 !important;\n'
        f'}}\n'
        f'.leaflet-container a.leaflet-popup-close-button:hover {{\n'
        f'  color: {t_text} !important;\n'
        f'}}\n'
        '</style>\n'
    )
    m.get_root().header.add_child(folium.Element(popup_header_html))

    # ── Walking-limit radius circle ────────────────────────────────────────
    radius_m = _walking_radius_metres(walking_limit_minutes)
    folium.Circle(
        location=[campus_lat, campus_lng],
        radius=radius_m,
        color=t_primary,
        weight=2,
        dash_array="6 4",
        fill=True,
        fill_color=t_primary,
        fill_opacity=0.05,
        tooltip=f"{int(walking_limit_minutes)} min walk radius",
    ).add_to(m)

    # ── Campus origin marker ───────────────────────────────────────────────
    folium.Marker(
        location=[campus_lat, campus_lng],
        tooltip="You are here (UCL Main Quad)",
        icon=folium.DivIcon(
            html=_campus_marker_icon_html(),
            icon_size=(34, 34),
            icon_anchor=(17, 17),
            popup_anchor=(0, -17),
            class_name="",
        ),
    ).add_to(m)

    # ── Build lookup: shop_id → (rank, lunch) ──────────────────────────────
    # Deduplicate shops so primary shop (#1) is never overwritten by alternatives at the same shop
    ranked_index: dict[str, tuple[int, Lunch]] = {}
    for lunch in ranked_lunches:
        if lunch.shop.shop_id not in ranked_index:
            ranked_index[lunch.shop.shop_id] = (len(ranked_index) + 1, lunch)

    # ── Shop markers ───────────────────────────────────────────────────────
    for shop in all_shops:
        if shop.lat == 0 and shop.lng == 0:
            continue  # skip shops with no coordinates

        btn_style = (
            f"display:block;width:100%;box-sizing:border-box;text-align:center;"
            f"padding:7px {t_space_3};margin-top:{t_space_3};background:{t_primary};color:{t_on_primary};"
            f"border-radius:{t_radius_button};text-decoration:none;{css_label};font-weight:600;cursor:pointer;"
        )
        onclick_js = (
            f"try {{ window.top.location.href = '/?shop=' + encodeURIComponent('{shop.shop_id}'); }} "
            f"catch (e) {{ try {{ window.parent.location.href = '/?shop=' + encodeURIComponent('{shop.shop_id}'); }} catch (err) {{}} }} "
            f"return false;"
        )
        view_btn_html = (
            f'<a href="/?shop={shop.shop_id}" '
            f'target="_top" '
            f'onclick="{onclick_js}" '
            f'style="{btn_style}">'
            f'View basket →</a>'
        )

        logo = logo_html(shop, size=22, standalone=True)

        is_open = is_shop_open(shop.shop_id, now)
        status_label = "Open Now" if is_open else "Closed"
        status_bg = t_success_tint if is_open else t_sample_tint
        status_ink = t_success_ink if is_open else t_text_muted
        status_border = f"border:{t_hairline} solid {t_border};" if not is_open else ""
        status_badge_html = (
            f'<span style="display:inline-flex;align-items:center;padding:2px {t_space_2};'
            f'border-radius:{t_radius_chip};background:{status_bg};color:{status_ink};{status_border}'
            f'{css_caption};font-weight:600;">{status_label}</span>'
        )
        hours_str = get_formatted_hours(shop.shop_id, now)
        hours_span = f'<span>🕒 {hours_str}</span>' if hours_str else ''
        hours_row_html = (
            f'<div style="{css_small};color:{t_text_muted};margin-bottom:{t_space_2};'
            f'display:flex;align-items:center;gap:{t_space_2};flex-wrap:wrap;">'
            f'{hours_span}{status_badge_html}'
            f'</div>'
        )

        if shop.shop_id in ranked_index:
            rank, lunch = ranked_index[shop.shop_id]
            rank_bg = _rank_colour(rank)
            deal_label = "Meal deal" if lunch.used_deal else "Separate"

            header_html = (
                f'<div style="display:flex;align-items:center;margin-bottom:{t_space_1};">'
                f'{logo}'
                f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                f'padding:2px 6px;margin-right:{t_space_2};border-radius:{t_radius_chip};background:{rank_bg};'
                f'color:{t_rank_ink};{css_caption};font-weight:700;">#{rank}</span>'
                f'<div style="{css_h3};color:{t_text};font-weight:700;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{shop.name}</div>'
                f'</div>'
            )

            walk_html = f'<div style="{css_small};color:{t_text_muted};margin-bottom:{t_space_2};">🚶 {shop.walking_minutes:.0f} min walk</div>'
            basket_html = (
                f'<div style="{css_body};color:{t_text};line-height:1.35;margin-bottom:{t_space_2};">'
                f'{lunch.main.name} + {lunch.snack.name} + {lunch.drink.name}'
                f'</div>'
            )

            deal_badge_html = (
                f'<span style="display:inline-flex;align-items:center;padding:2px {t_space_2};'
                f'border-radius:{t_radius_chip};background:{t_primary_tint};color:{t_primary};'
                f'{css_caption};font-weight:600;">{deal_label}</span>'
            )

            sample_badge_html = ""
            if is_sample(lunch):
                sample_badge_html = (
                    f'<span style="display:inline-flex;align-items:center;padding:2px {t_space_2};'
                    f'border-radius:{t_radius_chip};background:{t_sample_tint};color:{t_sample};'
                    f'border:{t_hairline} dashed {t_sample_outline};{css_caption};font-weight:600;">'
                    f'Sample data</span>'
                )

            price_row_html = (
                f'<div style="display:flex;align-items:center;gap:{t_space_2};flex-wrap:wrap;">'
                f'<span style="{css_price_sm};font-weight:700;color:{t_text};'
                f'font-variant-numeric:tabular-nums;">£{lunch.price_gbp:.2f}</span>'
                f'{deal_badge_html}'
                f'{sample_badge_html}'
                f'</div>'
            )

            popup_html = (
                f'<div style="font-family:Figtree,system-ui,sans-serif;">'
                f'{header_html}{walk_html}{hours_row_html}{basket_html}{price_row_html}{view_btn_html}'
                f'</div>'
            )
            marker_tooltip = f"#{rank} {shop.name}" + (" (sample data)" if is_sample(lunch) else "")
            icon_html = _marker_icon_html(shop, rank=rank)
        else:
            header_html = (
                f'<div style="display:flex;align-items:center;margin-bottom:{t_space_1};">'
                f'{logo}'
                f'<div style="{css_h3};color:{t_text};font-weight:700;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{shop.name}</div>'
                f'</div>'
            )
            walk_html = f'<div style="{css_small};color:{t_text_muted};margin-bottom:{t_space_2};">🚶 {shop.walking_minutes:.0f} min walk</div>'
            filter_badge = (
                f'<span style="display:inline-flex;align-items:center;padding:2px {t_space_2};'
                f'border-radius:{t_radius_chip};background:{t_sample_tint};color:{t_text_muted};'
                f'{css_caption};font-weight:600;">Outside your filters</span>'
            )
            popup_html = (
                f'<div style="font-family:Figtree,system-ui,sans-serif;">'
                f'{header_html}{walk_html}{hours_row_html}{filter_badge}{view_btn_html}'
                f'</div>'
            )
            marker_tooltip = shop.name
            icon_html = _marker_icon_html(shop, rank=None)

        folium.Marker(
            location=[shop.lat, shop.lng],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=marker_tooltip,
            icon=folium.DivIcon(
                html=icon_html,
                icon_size=(36, 36),
                icon_anchor=(18, 18),
                popup_anchor=(0, -20),
                class_name="",
            ),
        ).add_to(m)

    return m
