"""Sidebar filters (allergy / diet / meat chips) drive Preferences, via AppTest."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

import db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception, at.exception
    return at


def test_allergy_diet_and_meat_chips_set_filters(app):
    app.session_state["allergens_avoid"] = ["Nuts", "Milk"]
    app.session_state["diets"] = ["Vegetarian"]
    app.session_state["meats_allowed"] = ["Chicken"]
    app.run()
    assert not app.exception
    filter_captions = [c.value for c in app.caption if c.value.startswith("Filters:")]
    assert not filter_captions
    assert list(app.session_state["allergens_avoid"]) == ["Nuts", "Milk"]
    assert list(app.session_state["diets"]) == ["Vegetarian"]
    assert list(app.session_state["meats_allowed"]) == ["Chicken"]


def test_clear_diet_keeps_allergies(app):
    app.session_state["allergens_avoid"] = ["Gluten"]
    app.session_state["diets"] = ["Vegan"]
    app.session_state["meats_allowed"] = ["Fish"]
    app.run()
    app.session_state["_clear_diet_pending"] = True
    app.run()
    assert not app.exception
    assert list(app.session_state["diets"]) == [] and list(app.session_state["meats_allowed"]) == []
    assert list(app.session_state["allergens_avoid"]) == ["Gluten"]


def test_no_allergy_warning_box_in_filters(app):
    boxes = [m.value for m in app.sidebar.markdown if "dl-box--allergy" in m.value]
    assert not boxes


def test_sort_by_is_outside_sidebar_and_in_main_view(app):
    sidebar_selects = [s.label for s in app.sidebar.selectbox]
    assert "Sort by" not in sidebar_selects

    main_selects = [s.label for s in app.selectbox if s not in app.sidebar.selectbox]
    assert "Sort by" in main_selects

    sort_box = [s for s in app.selectbox if s.label == "Sort by"][0]
    sort_box.select("Distance").run()
    assert not app.exception
    assert app.session_state["sort_select"] == "Distance"


def test_screen_detail_has_no_item_selectors_above_names(app):
    app.query_params["shop"] = "sainsburys-warren-st"
    app.run()
    assert not app.exception
    assert app.session_state["screen"] == "detail"
    detail_selects = [s.label for s in app.selectbox]
    assert "Main" not in detail_selects
    assert "Snack" not in detail_selects
    assert "Drink" not in detail_selects
    swap_buttons = [b for b in app.button if b.label == "Swap in"]
    assert len(swap_buttons) > 0


