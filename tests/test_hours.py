"""
Tests for supermarket opening hours, open/closed evaluation, and open-now filtering.
"""

from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
from streamlit.testing.v1 import AppTest

import db
from hours import (
    SHOP_HOURS,
    SUPPORTED_SHOP_IDS,
    get_day_index,
    get_formatted_hours,
    get_shop_hours,
    get_status_label,
    is_shop_open,
    parse_hours,
    parse_time,
)
from models import Preferences, Shop
from optimiser import (
    _row_to_deal,
    _row_to_item,
    _row_to_shop,
    get_results,
    rank_shops,
)
from map_view import build_map

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# R1: Supermarket Hours Data Verification
# ---------------------------------------------------------------------------

def test_all_supported_shops_have_hours_for_every_day_of_week():
    expected_shops = {
        "tesco-tcr",
        "sainsburys-warren-st",
        "ms-tcr",
        "lidl-tcr",
        "waitrose-brunswick",
        "pret-tcr",
    }
    assert expected_shops == SUPPORTED_SHOP_IDS

    for shop_id in expected_shops:
        hours_by_day = SHOP_HOURS[shop_id]
        # Must have all 7 days of the week (0 to 6)
        assert set(hours_by_day.keys()) == set(range(7))
        for day_idx, (open_str, close_str) in hours_by_day.items():
            open_t = parse_time(open_str)
            close_t = parse_time(close_str)
            assert open_t < close_t, f"{shop_id} day {day_idx} has invalid hours: {open_str} - {close_str}"


def test_day_of_week_variations():
    """Verify that shops account for day-of-week variations (e.g. Sunday trading hours)."""
    # M&S Food TCR: Weekday closes at 21:00; Sunday restricted to 12:00 - 18:00
    ms_mon = SHOP_HOURS["ms-tcr"][0]
    ms_sun = SHOP_HOURS["ms-tcr"][6]
    assert ms_mon == ("07:00", "21:00")
    assert ms_sun == ("12:00", "18:00")
    assert ms_mon != ms_sun

    # Lidl TCR: Weekday 07:00 - 22:00; Sunday restricted to 11:00 - 17:00
    lidl_mon = SHOP_HOURS["lidl-tcr"][0]
    lidl_sun = SHOP_HOURS["lidl-tcr"][6]
    assert lidl_mon == ("07:00", "22:00")
    assert lidl_sun == ("11:00", "17:00")
    assert lidl_mon != lidl_sun

    # Waitrose Brunswick: Weekday 07:30 - 21:00; Sunday restricted to 12:00 - 18:00
    waitrose_mon = SHOP_HOURS["waitrose-brunswick"][0]
    waitrose_sun = SHOP_HOURS["waitrose-brunswick"][6]
    assert waitrose_mon == ("07:30", "21:00")
    assert waitrose_sun == ("12:00", "18:00")
    assert waitrose_mon != waitrose_sun

    # Pret TCR: Weekday closes at 19:30; Saturday at 18:30; Sunday at 17:30
    pret_fri = SHOP_HOURS["pret-tcr"][4]
    pret_sat = SHOP_HOURS["pret-tcr"][5]
    pret_sun = SHOP_HOURS["pret-tcr"][6]
    assert pret_fri == ("06:30", "19:30")
    assert pret_sat == ("07:30", "18:30")
    assert pret_sun == ("08:30", "17:30")

    # Tesco TCR convenience hours
    tesco_mon = SHOP_HOURS["tesco-tcr"][0]
    tesco_sat = SHOP_HOURS["tesco-tcr"][5]
    assert tesco_mon == ("06:00", "23:00")
    assert tesco_sat == ("07:00", "23:00")

    # Sainsbury's Warren St convenience hours
    sains_mon = SHOP_HOURS["sainsburys-warren-st"][0]
    sains_sun = SHOP_HOURS["sainsburys-warren-st"][6]
    assert sains_mon == ("07:00", "23:00")
    assert sains_sun == ("08:00", "23:00")


# ---------------------------------------------------------------------------
# Parsing and helper tests
# ---------------------------------------------------------------------------

def test_parse_time():
    assert parse_time("07:00") == time(7, 0)
    assert parse_time("7:00") == time(7, 0)
    assert parse_time("23:30:15") == time(23, 30, 15)
    assert parse_time("7:00 AM") == time(7, 0)
    assert parse_time("11:30 PM") == time(23, 30)
    assert parse_time("12:00 PM") == time(12, 0)
    assert parse_time("12:00 AM") == time(0, 0)

    with pytest.raises(ValueError):
        parse_time("invalid")
    with pytest.raises(ValueError):
        parse_time("25:00")


def test_parse_hours():
    t_open, t_close = parse_hours("07:00 - 23:00")
    assert t_open == time(7, 0)
    assert t_close == time(23, 0)

    # Unicode en-dash support
    t_open, t_close = parse_hours("08:00 – 22:00")
    assert t_open == time(8, 0)
    assert t_close == time(22, 0)

    # Unicode em-dash support
    t_open, t_close = parse_hours("06:30 — 19:30")
    assert t_open == time(6, 30)
    assert t_close == time(19, 30)

    # 12-hour AM/PM support
    t_open, t_close = parse_hours("7:00 AM - 11:00 PM")
    assert t_open == time(7, 0)
    assert t_close == time(23, 0)

    with pytest.raises(ValueError):
        parse_hours("07:00 to 23:00")


def test_get_day_index():
    # Integer
    assert get_day_index(0) == 0
    assert get_day_index(6) == 6
    assert get_day_index(7) == 0

    # String
    assert get_day_index("monday") == 0
    assert get_day_index("Mon") == 0
    assert get_day_index("sunday") == 6
    assert get_day_index("Sun") == 6

    # Date / datetime
    # 2026-10-16 is a Friday (index 4)
    dt = datetime(2026, 10, 16, 12, 0)
    d = date(2026, 10, 16)
    assert get_day_index(dt) == 4
    assert get_day_index(d) == 4


def test_get_shop_hours_and_formatted_hours():
    assert get_shop_hours("tesco-tcr", "monday") == ("06:00", "23:00")
    assert get_formatted_hours("tesco-tcr", "monday") == "06:00 - 23:00"

    # Unknown shop
    assert get_shop_hours("nonexistent-shop") is None
    assert get_formatted_hours("nonexistent-shop") == ""


# ---------------------------------------------------------------------------
# R2: Dedicated Open/Closed Evaluation & Boundary Minutes Tests
# ---------------------------------------------------------------------------

def test_boundary_minutes_opening_and_closing():
    """
    On Monday, Sainsbury's Warren St is open 07:00 - 23:00.
    Opening minute (07:00) is inclusive.
    Closing minute (23:00) is exclusive (shop is closed at 23:00:00).
    """
    # 2026-10-12 is a Monday
    # 06:59:59 -> Closed
    dt_before_open = datetime(2026, 10, 12, 6, 59, 59)
    assert not is_shop_open("sainsburys-warren-st", dt_before_open)

    # 07:00:00 -> Open
    dt_at_open = datetime(2026, 10, 12, 7, 0, 0)
    assert is_shop_open("sainsburys-warren-st", dt_at_open)

    # 12:30:00 -> Open
    dt_midday = datetime(2026, 10, 12, 12, 30, 0)
    assert is_shop_open("sainsburys-warren-st", dt_midday)

    # 22:59:59 -> Open
    dt_before_close = datetime(2026, 10, 12, 22, 59, 59)
    assert is_shop_open("sainsburys-warren-st", dt_before_close)

    # 23:00:00 -> Closed
    dt_at_close = datetime(2026, 10, 12, 23, 0, 0)
    assert not is_shop_open("sainsburys-warren-st", dt_at_close)

    # 23:01:00 -> Closed
    dt_after_close = datetime(2026, 10, 12, 23, 1, 0)
    assert not is_shop_open("sainsburys-warren-st", dt_after_close)


def test_sunday_trading_hours_evaluation():
    """
    On Sunday 2026-10-18:
    - M&S TCR is open 12:00 - 18:00
    - Lidl TCR is open 11:00 - 17:00
    - Tesco TCR is open 07:00 - 23:00
    """
    sunday = date(2026, 10, 18)

    # At 10:30 on Sunday:
    # Tesco is open (opens 07:00)
    # Lidl is closed (opens 11:00)
    # M&S is closed (opens 12:00)
    t_1030 = datetime.combine(sunday, time(10, 30))
    assert is_shop_open("tesco-tcr", t_1030)
    assert not is_shop_open("lidl-tcr", t_1030)
    assert not is_shop_open("ms-tcr", t_1030)

    # At 11:30 on Sunday:
    # Tesco is open
    # Lidl is open
    # M&S is still closed
    t_1130 = datetime.combine(sunday, time(11, 30))
    assert is_shop_open("tesco-tcr", t_1130)
    assert is_shop_open("lidl-tcr", t_1130)
    assert not is_shop_open("ms-tcr", t_1130)

    # At 14:00 on Sunday:
    # All three are open
    t_1400 = datetime.combine(sunday, time(14, 0))
    assert is_shop_open("tesco-tcr", t_1400)
    assert is_shop_open("lidl-tcr", t_1400)
    assert is_shop_open("ms-tcr", t_1400)

    # At 17:30 on Sunday:
    # Tesco is open
    # Lidl is closed (closed at 17:00)
    # M&S is open (closes at 18:00)
    t_1730 = datetime.combine(sunday, time(17, 30))
    assert is_shop_open("tesco-tcr", t_1730)
    assert not is_shop_open("lidl-tcr", t_1730)
    assert is_shop_open("ms-tcr", t_1730)

    # At 18:30 on Sunday:
    # Tesco is open
    # Lidl is closed
    # M&S is closed
    t_1830 = datetime.combine(sunday, time(18, 30))
    assert is_shop_open("tesco-tcr", t_1830)
    assert not is_shop_open("lidl-tcr", t_1830)
    assert not is_shop_open("ms-tcr", t_1830)


def test_status_label():
    dt_open = datetime(2026, 10, 16, 12, 0)
    dt_closed = datetime(2026, 10, 16, 3, 0)
    assert get_status_label("tesco-tcr", dt_open) == "Open Now"
    assert get_status_label("tesco-tcr", dt_closed) == "Closed"


def test_london_timezone_handling_utc_aware():
    """
    On Wednesday 2026-07-15, London is in British Summer Time (BST = UTC+1).
    At 06:15 UTC, London local time is 07:15 BST.
    Sainsbury's Warren St opens at 07:00 London time.
    A timezone-aware UTC datetime of 06:15 UTC must evaluate as OPEN in London.
    """
    dt_utc_morning = datetime(2026, 7, 15, 6, 15, tzinfo=timezone.utc)
    # 06:15 UTC -> 07:15 BST: Sainsbury's opens at 07:00, so open!
    assert is_shop_open("sainsburys-warren-st", dt_utc_morning)
    # Waitrose opens at 07:30 BST: at 07:15 BST, it is still closed!
    assert not is_shop_open("waitrose-brunswick", dt_utc_morning)

    # In the evening, Waitrose closes at 21:00 BST (20:00 UTC).
    # At 20:30 UTC, it is 21:30 BST: Waitrose is CLOSED!
    dt_utc_night = datetime(2026, 7, 15, 20, 30, tzinfo=timezone.utc)
    assert not is_shop_open("waitrose-brunswick", dt_utc_night)
    # Tesco closes at 23:00 BST (22:00 UTC): at 20:30 UTC (21:30 BST) Tesco is still OPEN!
    assert is_shop_open("tesco-tcr", dt_utc_night)


def test_daylight_saving_transition():
    """
    Test behaviour across the UK daylight saving transition.
    In 2026, UK clocks go back 1 hour from BST (UTC+1) to GMT (UTC+0) on Sunday 25 October at 02:00 BST (01:00 UTC).
    During daytime trading hours (e.g. 13:00), local hours evaluate accurately.
    """
    # Summer (BST, UTC+1): 12:00 UTC is 13:00 London local time
    summer_dt = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    assert is_shop_open("tesco-tcr", summer_dt)

    # Winter (GMT, UTC+0): 12:00 UTC is 12:00 London local time
    winter_dt = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
    assert is_shop_open("tesco-tcr", winter_dt)

    # On Sunday 25 Oct 2026 at 13:00 London time (GMT after transition):
    # Lidl is open 11:00 - 17:00
    post_transition = datetime(2026, 10, 25, 13, 0, tzinfo=ZoneInfo("Europe/London"))
    assert is_shop_open("lidl-tcr", post_transition)


def test_is_shop_open_date_input():
    """is_shop_open handles date objects without raising AttributeError."""
    d = date(2026, 10, 16)
    # Should not raise exception
    result = is_shop_open("tesco-tcr", d)
    assert isinstance(result, bool)


def test_known_shop_without_hours_is_closed(monkeypatch):
    """If a known shop has no hours defined for a particular day (closed all day), it returns False."""
    custom_hours = {
        "ms-tcr": {
            0: ("07:00", "21:00"),
            # Day 6 (Sunday) is omitted / None (closed all day)
        }
    }
    monkeypatch.setattr("hours.SHOP_HOURS", custom_hours)
    sunday_dt = datetime(2026, 10, 18, 14, 0)  # Sunday
    assert not is_shop_open("ms-tcr", sunday_dt)
    assert get_formatted_hours("ms-tcr", sunday_dt) == ""


# ---------------------------------------------------------------------------
# R3: "Open Now Only" Filter in Optimiser & Map
# ---------------------------------------------------------------------------

def test_optimiser_open_now_only_filtering():
    conn = db.get_connection()
    shops = [_row_to_shop(r) for r in db.fetch_all_shops(conn)]
    items = [_row_to_item(r) for r in db.fetch_approved_items(conn)]
    deals = [_row_to_deal(r) for r in db.fetch_approved_deals(conn)]

    # Sunday 2026-10-18 at 20:00:
    # Pret, Lidl, Waitrose, M&S are CLOSED.
    # Tesco (closes 23:00) and Sainsbury's (closes 23:00) are OPEN.
    sunday_night = datetime(2026, 10, 18, 20, 0)

    # With open_now_only=False (default): all qualifying shops ranked
    prefs_all = Preferences(open_now_only=False)
    ranked_all = rank_shops(shops, items, deals, prefs_all, now=sunday_night)
    all_shop_ids = {l.shop.shop_id for l in ranked_all}
    assert len(all_shop_ids) > 2  # Includes shops that are closed at 20:00 on Sunday

    # With open_now_only=True: only open shops ranked
    prefs_open = Preferences(open_now_only=True)
    ranked_open = rank_shops(shops, items, deals, prefs_open, now=sunday_night)
    open_shop_ids = {l.shop.shop_id for l in ranked_open}

    # All returned shops must be open
    for sid in open_shop_ids:
        assert is_shop_open(sid, sunday_night)

    # Closed shops must not be in the results
    assert "ms-tcr" not in open_shop_ids
    assert "lidl-tcr" not in open_shop_ids
    assert "waitrose-brunswick" not in open_shop_ids
    assert "pret-tcr" not in open_shop_ids

    # get_results also excludes closed shops
    primary, alts, others = get_results(shops, items, deals, prefs_open, now=sunday_night)
    if primary:
        assert is_shop_open(primary.shop.shop_id, sunday_night)
    for alt in alts:
        assert is_shop_open(alt.shop.shop_id, sunday_night)
    for other in others:
        assert is_shop_open(other.shop.shop_id, sunday_night)


def test_map_view_open_now_only_and_marker_content():
    conn = db.get_connection()
    shops = [_row_to_shop(r) for r in db.fetch_all_shops(conn)]
    items = [_row_to_item(r) for r in db.fetch_approved_items(conn)]
    deals = [_row_to_deal(r) for r in db.fetch_approved_deals(conn)]

    sunday_night = datetime(2026, 10, 18, 20, 0)
    primary, alts, others = get_results(shops, items, deals, Preferences(), now=sunday_night)
    ranked = [primary] + others if primary else []

    # 1. Map without open_now_only contains all shops and status badges in popups
    m_all = build_map(ranked, shops, open_now_only=False, now=sunday_night)
    rendered_all = m_all.get_root().render()

    # Operating hours and both status badges appear in popups
    assert "Open Now" in rendered_all
    assert "Closed" in rendered_all
    assert "07:00 - 23:00" in rendered_all or "06:00 - 23:00" in rendered_all

    # 2. Map with open_now_only=True excludes closed shops
    m_open = build_map(ranked, shops, open_now_only=True, now=sunday_night)
    rendered_open = m_open.get_root().render()

    # Closed shops (M&S, Lidl, Waitrose, Pret) must NOT appear on the map
    assert "ms-tcr" not in rendered_open
    assert "lidl-tcr" not in rendered_open
    assert "pret-tcr" not in rendered_open
    assert "waitrose-brunswick" not in rendered_open

    # Open shops (Tesco TCR, Sainsbury's Warren St) must appear
    assert "tesco-tcr" in rendered_open
    assert "sainsburys-warren-st" in rendered_open


# ---------------------------------------------------------------------------
# Streamlit AppTest: UI Integration
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_hours.db")
    monkeypatch.setattr(db, "_conn", None)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    return at


def test_ui_list_view_displays_hours_and_status_badge(fresh_app):
    """Test that operating hours and Open Now / Closed status badges render cleanly in List view."""
    # Run app on find screen
    fresh_app.run()
    assert not fresh_app.exception

    # Find the markdown content of result cards
    all_markdown = [m.value for m in fresh_app.markdown]
    combined_md = " ".join(all_markdown)

    # Status badges must appear
    assert "dl-badge--open" in combined_md or "dl-badge--closed" in combined_md
    assert "Open Now" in combined_md or "Closed" in combined_md

    # Formatted operating hours must appear
    assert "dl-card__hours" in combined_md
    assert " - " in combined_md  # e.g. '07:00 - 23:00'


def test_ui_toggle_open_now_only(fresh_app):
    """Test that toggling 'Open now only' in the sidebar updates preferences and runs cleanly."""
    toggle_widget = fresh_app.sidebar.toggle(key="open_now_only")
    assert not toggle_widget.value
    toggle_widget.set_value(True)
    fresh_app.run()
    assert not fresh_app.exception

    # Check caption count reflects the filter
    captions = [c.value for c in fresh_app.caption]
    matching = [c for c in captions if "within" in c and "shops" in c]
    assert len(matching) > 0
    # Must indicate "shops open within"
    assert any("shops open within" in c for c in matching)


def test_ui_no_open_shops_relax_button(fresh_app, monkeypatch):
    """When no shops are open in range, info message and 'Show closed shops too' button appear and work."""
    # Mock all shops as closed by clearing operating hours for all shops
    monkeypatch.setattr("hours.SHOP_HOURS", {k: {} for k in SUPPORTED_SHOP_IDS})
    fresh_app.sidebar.toggle(key="open_now_only").set_value(True)
    fresh_app.run()
    assert not fresh_app.exception

    # Info message shown
    info_texts = [info.value for info in fresh_app.info]
    assert any("No shops open within your walking limit" in text for text in info_texts)

    # Click 'Show closed shops too' button
    btn = fresh_app.button(key="disable_open_now")
    btn.click().run()
    assert not fresh_app.exception
    assert not fresh_app.session_state.get("open_now_only", False)
