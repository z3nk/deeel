"""Sidebar filters (allergy / diet / meat chips) drive Preferences, via AppTest."""

import pytest
from streamlit.testing.v1 import AppTest

import db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    at = AppTest.from_file("app.py", default_timeout=90).run()
    assert not at.exception, at.exception
    return at


def _summary(at) -> str:
    return next(c.value for c in at.caption if c.value.startswith("Filters:"))


def test_allergy_diet_and_meat_chips_set_filters(app):
    app.session_state["allergens_avoid"] = ["Nuts", "Milk"]
    app.session_state["diets"] = ["Vegetarian"]
    app.session_state["meats_allowed"] = ["Chicken"]
    app.run()
    assert not app.exception
    summary = _summary(app)
    assert "avoiding nuts, milk" in summary and "Vegetarian" in summary and "Chicken" in summary
    # the filter bar's allergy chips mirror the sidebar's
    assert list(app.session_state["allergens_avoid_quick"]) == ["Nuts", "Milk"]


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


def test_full_allergy_warning_box_in_filters(app):
    boxes = [m.value for m in app.sidebar.markdown if "dl-box--allergy" in m.value]
    assert boxes and "Always check the packaging yourself before eating." in boxes[0]
