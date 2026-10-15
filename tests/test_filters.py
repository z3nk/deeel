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
