"""
Tests for extract.py.
Claude calls are mocked — no API key or network needed.
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models import Confidence, Item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _make_item_json(overrides: dict = None) -> str:
    import json
    base = {
        "item_id": "test-001",
        "shop_id": "tesco-tcr",
        "name": "Chicken Caesar Wrap",
        "category": "main",
        "price_gbp": 3.50,
        "loyalty_price_gbp": None,
        "meal_deal_eligible": True,
        "temperature": "cold",
        "diet_flags": [],
        "allergens": ["gluten", "milk", "egg"],
        "ingredients_text": None,
        "premium_range": False,
        "quality_rating": None,
        "source_image": "tesco_wrap.jpg",
        "source_text": "£3.50 | Contains: gluten, milk, egg",
        "last_seen": "2026-10-12",
        "submitted_via": "upload",
        "submitted_by": None,
        "status": "pending",
        "confidence": "high",
        "needs_review": False,
    }
    if overrides:
        base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractItem:
    @patch("extract._get_client")
    def test_clear_label_returns_item(self, mock_get_client, tmp_path):
        """A fully readable label returns a validated Item."""
        # Create a dummy image file
        img_path = tmp_path / "tesco_wrap.jpg"
        from PIL import Image
        Image.new("RGB", (100, 100), color=(200, 200, 200)).save(img_path)

        mock_get_client.return_value.messages.create.return_value = (
            _mock_response(_make_item_json())
        )

        from extract import extract_item
        item = extract_item(img_path, "tesco-tcr", date(2026, 10, 12), strip_location=False)

        assert isinstance(item, Item)
        assert item.shop_id == "tesco-tcr"
        assert item.name == "Chicken Caesar Wrap"
        assert item.confidence == "high"
        assert item.needs_review is False
        assert "gluten" in item.allergens

    @patch("extract._get_client")
    def test_partial_label_sets_needs_review(self, mock_get_client, tmp_path):
        """A medium-confidence response forces needs_review=True."""
        img_path = tmp_path / "blurry.jpg"
        from PIL import Image
        Image.new("RGB", (100, 100)).save(img_path)

        mock_get_client.return_value.messages.create.return_value = (
            _mock_response(
                _make_item_json({"confidence": "medium", "needs_review": False})
            )
        )

        from extract import extract_item
        item = extract_item(img_path, "tesco-tcr", strip_location=False)

        assert item.needs_review is True
        assert item.confidence == "medium"

    @patch("extract._get_client")
    def test_unreadable_label_sets_needs_review(self, mock_get_client, tmp_path):
        """A low-confidence response forces needs_review=True."""
        img_path = tmp_path / "dark.jpg"
        from PIL import Image
        Image.new("RGB", (100, 100), color=(0, 0, 0)).save(img_path)

        mock_get_client.return_value.messages.create.return_value = (
            _mock_response(
                _make_item_json({"confidence": "low", "needs_review": False})
            )
        )

        from extract import extract_item
        item = extract_item(img_path, "tesco-tcr", strip_location=False)

        assert item.needs_review is True
        assert item.confidence == "low"

    @patch("extract._get_client")
    def test_diet_flags_only_from_label(self, mock_get_client, tmp_path):
        """Items with no printed diet flags have an empty list, not inferred flags."""
        img_path = tmp_path / "plain_sandwich.jpg"
        from PIL import Image
        Image.new("RGB", (100, 100)).save(img_path)

        mock_get_client.return_value.messages.create.return_value = (
            _mock_response(_make_item_json({"diet_flags": [], "allergens": []}))
        )

        from extract import extract_item
        item = extract_item(img_path, "tesco-tcr", strip_location=False)

        assert item.diet_flags == []
        assert item.allergens == []
