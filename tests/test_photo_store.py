"""Tests for photo_store.py and multi-product extraction (Claude mocked)."""

import io
import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import photo_store
from extract import build_deal, build_item, extract_photo


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_store, "UPLOAD_ROOT", tmp_path)
    return tmp_path


def _jpeg(size=(400, 300), exif_orientation=None, gps=False) -> bytes:
    img = Image.new("RGB", size, "red")
    exif = Image.Exif()
    if exif_orientation:
        exif[0x0112] = exif_orientation
    if gps:
        exif[0x8825] = {1: "N", 2: (51.0, 31.0, 0.0)}
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def test_files_by_shop_and_type(tmp_uploads):
    saved = photo_store.save_photo("tesco-tcr", "main", _jpeg(), today=date(2026, 10, 15))
    assert saved.path.parent == tmp_uploads / "tesco-tcr" / "main"
    assert saved.rel_path.startswith("tesco-tcr/main/2026-10-15_")
    assert not saved.already_existed


def test_same_photo_twice_is_detected():
    data = _jpeg()
    first = photo_store.save_photo("lidl-tcr", "drink", data)
    second = photo_store.save_photo("lidl-tcr", "drink", data)
    assert second.already_existed and second.path == first.path


def test_bad_inputs_rejected():
    with pytest.raises(ValueError):
        photo_store.save_photo("tesco-tcr", "dessert", _jpeg())
    with pytest.raises(ValueError):
        photo_store.save_photo("../etc", "main", _jpeg())


def test_exif_and_gps_removed_and_rotated_upright():
    saved = photo_store.save_photo("ms-tcr", "snack", _jpeg((400, 300), exif_orientation=6, gps=True))
    img = Image.open(saved.path)
    assert len(img.getexif()) == 0          # no GPS, no metadata at all
    assert img.size == (300, 400)           # orientation 6 = rotate 90° → portrait


def test_large_photos_shrunk():
    saved = photo_store.save_photo("ms-tcr", "general", _jpeg((5000, 3000)))
    assert max(Image.open(saved.path).size) == photo_store.MAX_SIDE


def test_storefront_banner(tmp_uploads):
    saved = photo_store.save_photo("pret-tcr", "general", _jpeg())
    photo_store.set_storefront("pret-tcr", saved.path)
    assert photo_store.storefront_upload("pret-tcr") == tmp_uploads / "pret-tcr" / "general" / "storefront.jpg"


# ---------------------------------------------------------------------------
# extract_photo — many products per photo
# ---------------------------------------------------------------------------

SHELF = {
    "kind": "shelf", "notes": "",
    "items": [
        {"name": "Chicken Caesar Wrap", "category": "main", "price_gbp": 3.5, "confidence": "high",
         "allergens": ["Milk"], "temperature": "cold", "source_text": "£3.50"},
        {"name": "Coke Zero", "category": "drink", "price_gbp": 1.2, "confidence": "high"},
        {"name": "Mystery pack", "category": "snack", "price_gbp": None, "confidence": "low"},
        {"category": "main"},                                    # no name → dropped
    ],
    "deals": [{"name": "Meal Deal", "price_gbp": 4.25, "loyalty_price_gbp": 3.85, "loyalty_scheme": "Clubcard"},
              {"name": "Meal Deal"}],                            # no price → dropped
}


def _mock_client(payload):
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text=json.dumps(payload))]
    return client


@patch("extract._get_client")
def test_general_photo_returns_every_product_and_deal(mock_get, tmp_uploads):
    mock_get.return_value = _mock_client(SHELF)
    saved = photo_store.save_photo("tesco-tcr", "general", _jpeg())
    result = extract_photo(saved.path, "tesco-tcr", "general")
    assert result.kind == "shelf"
    assert [i["name"] for i in result.items] == ["Chicken Caesar Wrap", "Coke Zero", "Mystery pack"]
    assert [i["category"] for i in result.items] == ["main", "drink", "snack"]
    assert len(result.deals) == 1


@patch("extract._get_client")
def test_specific_type_forces_category(mock_get):
    mock_get.return_value = _mock_client(SHELF)
    saved = photo_store.save_photo("tesco-tcr", "main", _jpeg())
    result = extract_photo(saved.path, "tesco-tcr", "main")
    assert {i["category"] for i in result.items} == {"main"}
    prompt = mock_get.return_value.messages.create.call_args.kwargs["messages"][0]["content"][1]["text"]
    assert "Only extract MAIN products" in prompt


def test_build_item_flags_low_confidence_for_review():
    item = build_item({"name": "Wrap", "category": "main", "price_gbp": 3, "confidence": "low",
                       "allergens": ["Milk"]}, "tesco-tcr", "tesco-tcr/main/x.jpg", date(2026, 10, 15), "u-sam")
    assert item.needs_review and item.status == "pending" and item.allergens == ["milk"]
    assert item.source_image == "tesco-tcr/main/x.jpg" and item.submitted_by == "u-sam"


def test_build_deal_normalises_unknown_values():
    deal = build_deal({"name": "Lunch thing", "price_gbp": 4, "loyalty_scheme": "Advantage"},
                      "tesco-tcr", "tesco-tcr/general/x.jpg", date(2026, 10, 15), None)
    assert deal.name == "Meal Deal" and deal.loyalty_scheme is None


def test_strip_gps_in_place_is_lossless(tmp_path):
    import hashlib
    import piexif
    path = tmp_path / "shelf.jpg"
    path.write_bytes(_jpeg(gps=True))
    exif = piexif.load(str(path))
    exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = b"2026:10:15 14:09:38"
    piexif.insert(piexif.dump(exif), str(path))
    pixels = hashlib.sha256(Image.open(path).tobytes()).hexdigest()

    assert photo_store.strip_gps_in_place(path) is True
    img = Image.open(path)
    assert not img.getexif().get_ifd(0x8825)
    assert hashlib.sha256(img.tobytes()).hexdigest() == pixels            # no re-encode
    assert piexif.load(str(path))["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"2026:10:15 14:09:38"
    assert photo_store.strip_gps_in_place(path) is False                   # nothing left to strip


# ---------------------------------------------------------------------------
# Meal deal (bundle) prices must not become item prices
# ---------------------------------------------------------------------------

from extract import drop_bundle_prices

TESCO_DEAL = [{"name": "Meal Deal", "price_gbp": 4.25, "loyalty_price_gbp": 3.85}]


def test_bundle_price_on_shelf_label_is_cleared():
    item = {"name": "Chicken Club", "price_gbp": 3.85, "source_text": "Meal Deal Main £3.85 Clubcard Price",
            "confidence": "high"}
    out = drop_bundle_prices(item, TESCO_DEAL)
    assert out["price_gbp"] is None and out["meal_deal_eligible"] is True and out["confidence"] == "medium"


def test_real_price_kept_even_if_label_mentions_meal_deal():
    item = {"name": "Chicken Club", "price_gbp": 3.50, "source_text": "£3.50 · Meal Deal Main", "confidence": "high"}
    assert drop_bundle_prices(item, TESCO_DEAL)["price_gbp"] == 3.50


def test_coincidental_same_price_without_deal_wording_kept():
    item = {"name": "Big Salad", "price_gbp": 4.25, "source_text": "£4.25", "confidence": "high"}
    assert drop_bundle_prices(item, TESCO_DEAL)["price_gbp"] == 4.25


def test_no_deals_in_photo_leaves_items_alone():
    item = {"name": "Wrap", "price_gbp": 3.95, "source_text": "Meal deal £3.95"}
    assert drop_bundle_prices(item, [])["price_gbp"] == 3.95


@patch("extract._get_client")
def test_extract_photo_applies_bundle_rule_and_prompt_says_so(mock_get):
    payload = {"kind": "shelf", "notes": "", "deals": [{"name": "Meal Deal", "price_gbp": 3.95}],
               "items": [{"name": "Tuna Mayo", "category": "main", "price_gbp": 3.95,
                          "source_text": "Meal deal £3.95", "confidence": "high"},
                         {"name": "Egg Mayo", "category": "main", "price_gbp": 2.10,
                          "source_text": "£2.10 Meal deal", "confidence": "high"}]}
    mock_get.return_value = _mock_client(payload)
    saved = photo_store.save_photo("sainsburys-warren-st", "main", _jpeg())
    result = extract_photo(saved.path, "sainsburys-warren-st", "main")
    assert [i["price_gbp"] for i in result.items] == [None, 2.10]
    system = mock_get.return_value.messages.create.call_args.kwargs["system"]
    assert "BUNDLE price, never the\n   item price" in system
