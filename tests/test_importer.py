"""Tests for importer.py — drag-and-drop inbox import (Claude mocked)."""

import io
from datetime import date
from unittest.mock import patch

import pytest
from PIL import Image

import db
import photo_store
from extract import PhotoExtraction
from importer import ensure_inbox, import_inbox, photo_taken_date


def _jpeg(colour="red", taken: str | None = None) -> bytes:
    img = Image.new("RGB", (300, 200), colour)
    exif = Image.Exif()
    if taken:
        exif[0x0132] = taken
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_store, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(db, "_auto_seed_items", lambda conn: None)   # no fallback rows
    conn = db.get_connection()
    inbox = tmp_path / "seed" / "inbox"
    ensure_inbox(inbox, ["tesco-tcr", "ms-tcr"])
    yield conn, inbox, tmp_path
    conn.close()


SHELF = PhotoExtraction(
    kind="shelf", notes="",
    items=[
        {"name": "Chicken Wrap", "category": "main", "price_gbp": 3.5, "confidence": "high", "kcal": 480},
        {"name": "Mystery Pot", "category": "snack", "price_gbp": None, "confidence": "low"},
    ],
    deals=[{"name": "Meal Deal", "price_gbp": 4.25, "loyalty_price_gbp": 3.85, "loyalty_scheme": "Clubcard"}],
)
STOREFRONT = PhotoExtraction(kind="storefront", notes="", items=[], deals=[])


def test_imports_queues_pending_and_moves_originals(env):
    conn, inbox, tmp = env
    (inbox / "tesco-tcr" / "general" / "IMG_1.jpg").write_bytes(_jpeg(taken="2026:10:14 12:30:00"))
    with patch("importer.extract_photo", return_value=SHELF):
        report = import_inbox(conn, inbox, workers=2, log=lambda m: None)

    assert (report.photos, report.items, report.deals) == (1, 1, 1)
    assert report.unpriced == ["tesco-tcr/general/IMG_1.jpg: Mystery Pot"]
    row = conn.execute("SELECT * FROM items").fetchone()
    assert row["status"] == "pending" and row["submitted_via"] == "seed" and row["submitted_by"] is None
    assert row["last_seen"] == "2026-10-14"                        # date the photo was TAKEN
    assert row["source_image"].startswith("tesco-tcr/general/2026-10-14_")
    assert conn.execute("SELECT status FROM deals").fetchone()[0] == "pending"
    # original moved, not deleted
    assert not (inbox / "tesco-tcr" / "general" / "IMG_1.jpg").exists()
    assert (tmp / "seed" / "inbox_done" / "tesco-tcr" / "general" / "IMG_1.jpg").exists()


def test_reimport_of_same_photo_is_skipped(env):
    conn, inbox, _ = env
    data = _jpeg("blue")
    (inbox / "ms-tcr" / "main" / "a.jpg").write_bytes(data)
    with patch("importer.extract_photo", return_value=SHELF):
        import_inbox(conn, inbox, log=lambda m: None)
        (inbox / "ms-tcr" / "main" / "a.jpg").write_bytes(data)
        report = import_inbox(conn, inbox, log=lambda m: None)
    assert report.duplicates == 1 and report.photos == 0
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_failed_photo_stays_in_inbox(env):
    conn, inbox, _ = env
    (inbox / "tesco-tcr" / "drink" / "blurry.jpg").write_bytes(_jpeg("green"))
    with patch("importer.extract_photo", side_effect=RuntimeError("API down")):
        report = import_inbox(conn, inbox, log=lambda m: None)
    assert report.failed and "API down" in report.failed[0]
    assert (inbox / "tesco-tcr" / "drink" / "blurry.jpg").exists()


def test_storefront_sets_banner_once(env):
    conn, inbox, _ = env
    (inbox / "tesco-tcr" / "general" / "front.jpg").write_bytes(_jpeg("yellow"))
    with patch("importer.extract_photo", return_value=STOREFRONT):
        report = import_inbox(conn, inbox, log=lambda m: None)
    assert report.banners == 1
    assert photo_store.storefront_upload("tesco-tcr") is not None


def test_unknown_folders_reported_not_imported(env):
    conn, inbox, _ = env
    (inbox / "asda-tcr" / "main").mkdir(parents=True)
    (inbox / "asda-tcr" / "main" / "x.jpg").write_bytes(_jpeg())
    (inbox / "tesco-tcr" / "dessert").mkdir()
    (inbox / "tesco-tcr" / "dessert" / "y.jpg").write_bytes(_jpeg("pink"))
    with patch("importer.extract_photo", return_value=SHELF) as mock:
        report = import_inbox(conn, inbox, log=lambda m: None)
    assert not mock.called
    assert sorted(report.skipped_folders) == ["asda-tcr/main", "tesco-tcr/dessert"]


def test_photo_taken_date():
    assert photo_taken_date(_jpeg(taken="2026:10:13 09:00:00")) == date(2026, 10, 13)
    assert photo_taken_date(_jpeg()) is None
    assert photo_taken_date(b"not an image") is None
