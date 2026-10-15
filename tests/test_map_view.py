"""Tests for map_view modernised pins, DivIcon logos, star badge, CartoDB tiles, and popup navigation."""

from pathlib import Path
import folium
from streamlit.testing.v1 import AppTest

from db import fetch_all_shops, fetch_approved_deals, fetch_approved_items, get_connection
from map_view import build_map, get_carto_tiles_url, CARTO_TILES_URL
from models import Preferences
from optimiser import _row_to_deal, _row_to_item, _row_to_shop, get_results
from shop_images import logo_data_uri

ROOT = Path(__file__).parent.parent


def test_get_carto_tiles_url(monkeypatch):
    monkeypatch.delenv("CARTO_API_KEY", raising=False)
    monkeypatch.delenv("CARTO_TILES_URL", raising=False)
    assert get_carto_tiles_url() == CARTO_TILES_URL

    monkeypatch.setenv("CARTO_API_KEY", "carto-test-key-1234")
    assert get_carto_tiles_url() == f"{CARTO_TILES_URL}?key=carto-test-key-1234"

    monkeypatch.setenv("CARTO_TILES_URL", "https://custom.tiles.example.com/{z}/{x}/{y}.png")
    assert get_carto_tiles_url() == "https://custom.tiles.example.com/{z}/{x}/{y}.png?key=carto-test-key-1234"


def test_logo_data_uri():
    assert logo_data_uri("tesco") is not None
    assert logo_data_uri("tesco").startswith("data:image/svg+xml;base64,")
    assert logo_data_uri("sainsburys") is not None
    assert logo_data_uri("pret") is not None
    assert logo_data_uri("unknown_chain") is None


def test_build_map_cartodb_tiles_and_logo_pins():
    conn = get_connection()
    shops = [_row_to_shop(r) for r in fetch_all_shops(conn)]
    items = [_row_to_item(r) for r in fetch_approved_items(conn)]
    deals = [_row_to_deal(r) for r in fetch_approved_deals(conn)]
    primary, alts, others = get_results(shops, items, deals, Preferences())
    ranked = [primary] + others if primary else []

    m = build_map(ranked, shops)
    rendered = m.get_root().render()

    # 1. Base tiles check
    assert "basemaps.cartocdn.com/light_all" in rendered
    assert "CARTO" in rendered

    # 2. Shop logos check
    assert "data:image/svg+xml;base64," in rendered

    # 3. Rank 1 star badge check
    assert ("<svg" in rendered or "\\u003csvg" in rendered)
    assert "M12 17.27L18.18 21" in rendered

    # 4. Single Marker check (no CircleMarker for shops)
    circle_markers = [child for child in m._children.values() if isinstance(child, folium.CircleMarker)]
    assert len(circle_markers) == 0


def test_build_map_shop_deduplication():
    conn = get_connection()
    shops = [_row_to_shop(r) for r in fetch_all_shops(conn)]
    items = [_row_to_item(r) for r in fetch_approved_items(conn)]
    deals = [_row_to_deal(r) for r in fetch_approved_deals(conn)]
    primary, alts, others = get_results(shops, items, deals, Preferences())

    # Ensure alternatives share primary shop
    assert len(alts) > 0
    assert alts[0].shop.shop_id == primary.shop.shop_id

    # Passing primary + alternatives + others must still assign rank 1 to primary
    ranked_with_alts = [primary] + alts + others
    m = build_map(ranked_with_alts, shops)
    rendered = m.get_root().render()

    # Rank 1 badge must appear on the primary shop in popup
    assert "#1</span>" in rendered
    assert primary.shop.name in rendered


def test_map_popup_navigation_script_and_styling():
    conn = get_connection()
    shops = [_row_to_shop(r) for r in fetch_all_shops(conn)]
    items = [_row_to_item(r) for r in fetch_approved_items(conn)]
    deals = [_row_to_deal(r) for r in fetch_approved_deals(conn)]
    primary, _, others = get_results(shops, items, deals, Preferences())
    ranked = [primary] + others if primary else []

    m = build_map(ranked, shops)
    rendered = m.get_root().render()

    # Verify inline navigation handler and styling
    assert "window.top.location.href" in rendered
    assert "target=\"_top\"" in rendered
    assert "?shop=" in rendered
    assert "leaflet-popup-content-wrapper" in rendered
    assert "View basket →" in rendered
    assert "Figtree" in rendered


def test_query_param_navigation():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.query_params["shop"] = "tesco-tcr"
    at.run()
    assert not at.exception
    assert at.session_state["screen"] == "detail"
    assert at.session_state["detail_shop_id"] == "tesco-tcr"
    assert "shop" not in at.query_params
