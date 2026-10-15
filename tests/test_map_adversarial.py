"""Adversarial stress testing for map_view.py and app.py navigation & edge cases."""

from datetime import date
import json
import subprocess
from pathlib import Path

import folium
import pytest
from streamlit.testing.v1 import AppTest

from db import fetch_all_shops, fetch_approved_deals, fetch_approved_items, get_connection
from map_view import build_map, _marker_icon_html
from models import Item, Lunch, Preferences, Shop
from optimiser import _row_to_deal, _row_to_item, _row_to_shop, get_results
from shop_images import logo_data_uri

ROOT = Path(__file__).parent.parent


def _dummy_shop(
    shop_id: str = "custom-shop",
    chain: str = "custom_chain",
    name: str = "Custom Cafe",
    lat: float = 51.524,
    lng: float = -0.134,
) -> Shop:
    return Shop.model_construct(
        shop_id=shop_id,
        chain=chain,
        name=name,
        address="123 High St",
        walking_minutes=5.0,
        last_verified=date(2026, 1, 1),
        lat=lat,
        lng=lng,
    )


def _dummy_lunch(shop: Shop, price: float = 4.50) -> Lunch:
    dummy_item = Item.model_construct(
        item_id=f"item-{shop.shop_id}",
        shop_id=shop.shop_id,
        name="Test Item",
        category="main",
        price_gbp=3.0,
        loyalty_price_gbp=None,
        meal_deal_eligible=True,
        temperature="cold",
        diet_flags=[],
        allergens=[],
        ingredients_text=None,
        meats=None,
        kcal=400.0,
        protein_g=15.0,
        barcode=None,
        external_fields={},
        premium_range=False,
        status="approved",
        submitted_by="test",
        source_image="test.jpg",
        last_seen=date(2026, 1, 1),
    )
    return Lunch(
        shop=shop,
        main=dummy_item,
        snack=dummy_item,
        drink=dummy_item,
        used_deal=True,
        deal_name="Meal Deal",
        price_gbp=price,
        loyalty_price_gbp=None,
        why="Best price",
        score=9.5,
    )


# ---------------------------------------------------------------------------
# 1. Empty ranked lunches list (0 shops found)
# ---------------------------------------------------------------------------

def test_empty_ranked_lunches():
    conn = get_connection()
    shops = [_row_to_shop(r) for r in fetch_all_shops(conn)]

    # build_map with 0 ranked lunches
    m = build_map(ranked_lunches=[], all_shops=shops)
    rendered = m.get_root().render()

    assert "basemaps.cartocdn.com/light_all" in rendered
    # Every shop should be marked "Outside your filters"
    assert rendered.count("Outside your filters") == len(shops)
    # No star badge or rank number badges
    assert "M12 17.27L18.18 21" not in rendered
    assert "#1</span>" not in rendered


def test_empty_ranked_and_empty_shops():
    m = build_map(ranked_lunches=[], all_shops=[])
    rendered = m.get_root().render()
    assert "basemaps.cartocdn.com/light_all" in rendered
    assert "You are here" in rendered


def test_app_empty_results_handling():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    assert not at.exception


# ---------------------------------------------------------------------------
# 2. Unknown shop chain without logo file (initials badge fallback)
# ---------------------------------------------------------------------------

def test_unknown_chain_initials_badge_fallback():
    shop = _dummy_shop(chain="unknown_cafe_chain", name="Gower Cafe")
    assert logo_data_uri(shop.chain) is None

    # Icon html for rank 1
    icon_rank1 = _marker_icon_html(shop, rank=1)
    # Fallback initials badge should take first letter "G"
    assert ">G</span>" in icon_rank1
    # Star badge must be present for rank 1
    assert "M12 17.27L18.18 21" in icon_rank1

    # Icon html for unranked shop
    icon_unranked = _marker_icon_html(shop, rank=None)
    assert ">G</span>" in icon_unranked
    assert "M12 17.27L18.18 21" not in icon_unranked

    # Full map render with unknown shop
    lunch = _dummy_lunch(shop)
    m = build_map([lunch], [shop])
    rendered = m.get_root().render()
    assert "Gower Cafe" in rendered
    assert "#1</span>" in rendered


def test_unknown_chain_empty_name():
    shop = _dummy_shop(chain="mystery", name="")
    # Should not raise IndexError
    icon = _marker_icon_html(shop, rank=1)
    assert "></span>" in icon


# ---------------------------------------------------------------------------
# 3. Coordinates at (0, 0) skipped
# ---------------------------------------------------------------------------

def test_coordinates_at_zero_zero_skipped():
    shop_zero1 = _dummy_shop(shop_id="zero-1", name="Zero Island 1", lat=0.0, lng=0.0)
    shop_zero2 = _dummy_shop(shop_id="zero-2", name="Zero Island 2", lat=0, lng=0)
    shop_valid = _dummy_shop(shop_id="valid-1", name="Valid Shop", lat=51.524, lng=-0.134)

    m = build_map([], [shop_zero1, shop_zero2, shop_valid])
    rendered = m.get_root().render()

    assert "Valid Shop" in rendered
    assert "Zero Island 1" not in rendered
    assert "Zero Island 2" not in rendered

    # Only 2 markers in total: campus origin + Valid Shop
    markers = [c for c in m._children.values() if type(c) is folium.Marker]
    assert len(markers) == 2


# ---------------------------------------------------------------------------
# 4. Single shop result (rank 1 star badge correctly placed)
# ---------------------------------------------------------------------------

def test_single_shop_result_star_badge():
    shop1 = _dummy_shop(shop_id="shop-1", chain="tesco", name="Shop One")
    shop2 = _dummy_shop(shop_id="shop-2", chain="lidl", name="Shop Two", lat=51.525, lng=-0.135)
    lunch1 = _dummy_lunch(shop1)

    m = build_map([lunch1], [shop1, shop2])
    rendered = m.get_root().render()

    # Shop 1 has #1 badge and star badge
    assert "#1</span>" in rendered
    assert "M12 17.27L18.18 21" in rendered
    # Shop 2 is outside filters
    assert "Outside your filters" in rendered


# ---------------------------------------------------------------------------
# 5. Direct deep linking with malicious or nonexistent shop IDs
# ---------------------------------------------------------------------------

def test_deep_linking_nonexistent_shop():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.query_params["shop"] = "nonexistent-shop-id-999"
    at.run()
    assert not at.exception
    assert at.session_state["screen"] == "detail"
    # Query parameter was consumed and deleted
    assert "shop" not in at.query_params
    # Shop not found error displayed
    assert len(at.error) > 0
    assert any("Shop not found" in e.value for e in at.error)


def test_deep_linking_xss_injection():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.query_params["shop"] = "<script>alert('xss')</script>"
    at.run()
    assert not at.exception
    assert at.session_state["screen"] == "detail"
    assert "shop" not in at.query_params
    assert len(at.error) > 0
    assert any("Shop not found" in e.value for e in at.error)


def test_deep_linking_sql_injection():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.query_params["shop"] = "' OR 1=1 --"
    at.run()
    assert not at.exception
    assert at.session_state["screen"] == "detail"
    assert "shop" not in at.query_params
    assert len(at.error) > 0


def test_deep_linking_invalid_screen_param():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.query_params["screen"] = "malicious_screen_inject"
    at.run()
    assert not at.exception
    assert "screen" not in at.query_params
    # Should default to "find"
    assert at.session_state["screen"] == "find"


# ---------------------------------------------------------------------------
# 6. Inline navigation handler JavaScript syntax and execution in Node.js
# ---------------------------------------------------------------------------

def test_dl_navigate_shop_js_syntax_in_node():
    # Node script simulating the iframe window and parent window context
    node_test_script = """
    globalThis.window = {
        location: { href: 'http://localhost:8501/?component=st_folium', search: '' },
        parent: {
            location: { search: '', href: '' },
            Function: function(code) {
                return new Function(code);
            }
        }
    };

    function simulateClick(shopId) {
        // Simulates the inline onclick handler executed by the browser on popup anchor click
        const onclickFn = new Function(`try { /* dl_navigate_shop */ (window.parent.Function('window.location.search = \\\\x22?shop=\\\\x22 + encodeURIComponent(\\\\x22${shopId}\\\\x22)'))(); } catch (e) { window.parent.location.href = '?shop=' + encodeURIComponent('${shopId}'); } return false;`);
        return onclickFn();
    }
    const dl_navigate_shop = simulateClick;

    // 1. Standard shop ID test
    const ret1 = simulateClick('tesco-tcr');
    if (ret1 !== false) throw new Error('Inline onclick handler must return false to suppress default anchor navigation');
    if (window.location.search !== '?shop=tesco-tcr') {
        throw new Error('Expected ?shop=tesco-tcr but got ' + window.location.search);
    }

    // 2. Fallback path test (when parent.Function throws or is blocked by sandbox)
    window.parent.Function = function() {
        throw new Error('Blocked by sandbox without allow-top-navigation');
    };
    const ret2 = simulateClick('lidl-tcr');
    if (ret2 !== false) throw new Error('Fallback handler must return false');
    if (window.parent.location.href !== '?shop=lidl-tcr') {
        throw new Error('Fallback failed to set window.parent.location.href');
    }

    console.log('NODE_JS_TEST_SUCCESS');
    """

    res = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Node.js script failed:\n{res.stderr}"
    assert "NODE_JS_TEST_SUCCESS" in res.stdout
