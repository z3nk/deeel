"""Tests for barcode fill: our data first, then Open Food Facts (network mocked)."""

import json
from datetime import date
from unittest.mock import patch

import pytest

import approval
import db
import openfoodfacts
from extract import build_item
from nutrition_fill import OUR_DATA, fill_existing, fill_missing
from openfoodfacts import normalise_barcode, per_pack

COKE = "5449000000996"          # valid EAN-13
OFF_COKE = {"kcal": 210.0, "protein_g": 0.0, "ingredients_text": "Carbonated water, sugar"}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(db, "_auto_seed_items", lambda c: None)
    openfoodfacts._cache.clear()
    c = db.get_connection()
    yield c
    c.close()


def _queue(conn, **fields):
    base = {"name": "Coke", "category": "drink", "price_gbp": 1.2, "confidence": "high"}
    item = build_item({**base, **fields}, "tesco-tcr", "tesco-tcr/drink/x.jpg", date(2026, 10, 15), None)
    data = item.model_dump(); data["last_seen"] = item.last_seen.isoformat()
    return approval.queue_item(conn, data)


# --- barcode validation + per-pack maths ---------------------------------

def test_barcode_check_digit():
    assert normalise_barcode(COKE) == COKE
    assert normalise_barcode("5449 0000 0099 6") == COKE
    assert normalise_barcode("5449000000997") is None      # one digit misread
    assert normalise_barcode("12345") is None
    assert normalise_barcode(None) is None


def test_per_pack_scales_by_quantity_or_leaves_empty():
    product = {"nutriments": {"energy-kcal_100g": 42, "proteins_100g": 0}, "product_quantity": "500",
               "ingredients_text_en": "Water, sugar"}
    assert per_pack(product) == {"kcal": 210.0, "protein_g": 0.0, "ingredients_text": "Water, sugar"}
    no_qty = {"nutriments": {"energy-kcal_100g": 42}}
    assert "kcal" not in per_pack(no_qty)


def test_pack_quantity_from_text_and_multipacks_skipped():
    from openfoodfacts import pack_quantity
    assert pack_quantity({"quantity": "330 ml"}) == 330
    assert pack_quantity({"quantity": "1.5 L"}) == 1500
    assert pack_quantity({"quantity": "4 x 330 ml"}) is None
    assert pack_quantity({"product_quantity": "0", "quantity": ""}) is None


# --- fill order -----------------------------------------------------------

def test_our_data_first_then_open_food_facts(conn):
    # We already photographed a Coke label elsewhere with kcal only
    _queue(conn, barcode=COKE, kcal=210)
    with patch("openfoodfacts._fetch", return_value={
        "nutriments": {"energy-kcal_100g": 99, "proteins_100g": 0}, "product_quantity": 500,
        "ingredients_text": "Carbonated water, sugar"}) as off:
        out = fill_missing(conn, {"name": "Coke", "barcode": COKE, "allergens": []})
    assert out["kcal"] == 210 and out["external_fields"]["kcal"] == OUR_DATA          # ours, not OFF's 495
    assert out["protein_g"] == 0.0 and out["external_fields"]["protein_g"] == openfoodfacts.SOURCE
    assert out["ingredients_text"] == "Carbonated water, sugar"
    assert off.call_count == 1


def test_open_food_facts_not_called_when_our_data_covers_it(conn):
    _queue(conn, barcode=COKE, kcal=210, protein_g=0, ingredients_text="Water, sugar", allergens=["caffeine"])
    with patch("openfoodfacts._fetch") as off:
        out = fill_missing(conn, {"name": "Coke", "barcode": COKE})
    assert not off.called and set(out["external_fields"].values()) == {OUR_DATA}


def test_label_values_never_overwritten(conn):
    with patch("openfoodfacts.lookup", return_value={**OFF_COKE, "allergens": ["milk"]}):
        out = fill_missing(conn, {"name": "Coke", "barcode": COKE, "kcal": 139, "allergens": ["gluten"]})
    assert out["kcal"] == 139 and "kcal" not in out["external_fields"]
    assert out["allergens"] == ["gluten"] and "allergens" not in out["external_fields"]


def test_open_food_facts_values_not_reused_as_our_data(conn):
    _queue(conn, barcode=COKE, kcal=210, external_fields={"kcal": openfoodfacts.SOURCE})
    with patch("openfoodfacts.lookup", return_value=None):
        out = fill_missing(conn, {"name": "Coke", "barcode": COKE})
    assert out.get("kcal") is None


def test_no_barcode_or_bad_barcode_does_nothing(conn):
    with patch("openfoodfacts._fetch") as off:
        assert fill_missing(conn, {"name": "Wrap"}) == {"name": "Wrap"}
        fill_missing(conn, {"name": "Wrap", "barcode": "5449000000997"})
    assert not off.called


def test_network_failure_leaves_gaps(conn):
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        out = fill_missing(conn, {"name": "Coke", "barcode": COKE})
    assert out.get("kcal") is None and out["external_fields"] == {}


def test_fill_existing_updates_db(conn):
    item_id = _queue(conn, barcode=COKE)
    with patch("openfoodfacts.lookup", return_value=OFF_COKE):
        checked, filled = fill_existing(conn)
    row = conn.execute("SELECT kcal, protein_g, ingredients_text, external_fields FROM items WHERE item_id=?",
                       (item_id,)).fetchone()
    assert (checked, filled) == (1, 3)
    assert row["kcal"] == 210.0 and json.loads(row["external_fields"])["kcal"] == openfoodfacts.SOURCE


# --- allergens ---------------------------------------------------------------

def test_off_allergen_tags_mapped_to_app_names():
    product = {"allergens_tags": ["en:milk", "en:peanuts", "en:crustaceans", "en:unknown-thing"]}
    assert per_pack(product)["allergens"] == ["milk", "nuts", "peanuts", "shellfish"]
    assert "allergens" not in per_pack({"allergens_tags": []})     # empty = not entered, not "none"


def test_missing_allergens_filled_and_sourced(conn):
    _queue(conn, barcode=COKE, allergens=["milk"])                  # our label of the same barcode
    out = fill_missing(conn, {"name": "Coke", "barcode": COKE, "allergens": []})
    assert out["allergens"] == ["milk"] and out["external_fields"]["allergens"] == OUR_DATA
    openfoodfacts._cache.clear()
    with patch("openfoodfacts.lookup", return_value={"allergens": ["gluten"]}):
        out = fill_missing(None, {"name": "Wrap", "barcode": COKE, "allergens": []})
    assert out["allergens"] == ["gluten"] and out["external_fields"]["allergens"] == openfoodfacts.SOURCE


def test_fill_existing_fills_allergens_in_db(conn):
    item_id = _queue(conn, barcode=COKE)
    with patch("openfoodfacts.lookup", return_value={"allergens": ["milk"]}):
        fill_existing(conn)
    row = conn.execute("SELECT allergens, external_fields FROM items WHERE item_id=?", (item_id,)).fetchone()
    assert json.loads(row["allergens"]) == ["milk"]
    assert json.loads(row["external_fields"])["allergens"] == openfoodfacts.SOURCE
