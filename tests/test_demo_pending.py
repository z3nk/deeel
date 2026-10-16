"""Demo review entries (seed/demo_pending.json) and the seeded photo tasks."""

import json
import shutil
from pathlib import Path

import approval
import db
import snapshot
from snapshot import export_snapshot, sync_demo_pending

ROOT = Path(__file__).resolve().parent.parent
DEMO_JSON = ROOT / "seed" / "demo_pending.json"
DEMO_PHOTOS = ROOT / "seed" / "demo_photos"


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    return db.get_connection()


def _sync(conn, tmp_path):
    return sync_demo_pending(conn, DEMO_JSON, DEMO_PHOTOS, tmp_path / "uploads")


def test_demo_entries_are_fully_filled_in():
    data = json.loads(DEMO_JSON.read_text())
    assert len(data["items"]) >= 4 and data["deals"]
    for item in data["items"]:
        assert item["item_id"].startswith("demo-")
        for field in ("name", "price_gbp", "ingredients_text", "kcal", "protein_g", "barcode",
                      "allergens", "meats", "temperature", "source_text"):
            assert item[field] not in (None, ""), (item["item_id"], field)
        assert item["confidence"] == "high" and not item["needs_review"]
        assert (DEMO_PHOTOS / item["source_image"]).exists()
    for deal in data["deals"]:
        assert deal["deal_id"].startswith("demo-") and deal["price_gbp"] and deal["loyalty_price_gbp"]
        assert (DEMO_PHOTOS / deal["source_image"]).exists()


def test_sync_queues_them_with_photos_and_never_twice(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch)
    total = len(json.loads(DEMO_JSON.read_text())["items"]) + len(json.loads(DEMO_JSON.read_text())["deals"])
    assert _sync(conn, tmp_path) == total
    assert _sync(conn, tmp_path) == 0                          # every startup is safe
    pending = approval.get_pending_items(conn)
    assert {r["item_id"] for r in pending} >= {"demo-pret-caesar-wrap", "demo-waitrose-egg-cress"}
    assert len(approval.get_pending_deals(conn)) == 1
    assert all(r["submitted_by"] is None for r in pending)
    for r in pending:
        assert (tmp_path / "uploads" / r["source_image"]).exists()


def test_approved_or_rejected_leave_the_queue_for_good(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch)
    _sync(conn, tmp_path)
    assert approval.approve(conn, "demo-pret-caesar-wrap", "item") == 0       # nobody to pay
    approval.reject(conn, "demo-ms-percy-pigs", "item")
    approval.approve(conn, "demo-deal-waitrose", "deal")
    _sync(conn, tmp_path)                                                    # restart
    assert "demo-pret-caesar-wrap" not in {r["item_id"] for r in approval.get_pending_items(conn)}
    assert "demo-ms-percy-pigs" not in {r["item_id"] for r in approval.get_pending_items(conn)}
    assert approval.get_pending_deals(conn) == []


def test_demo_entries_never_reach_shoppers_or_the_snapshot(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch)
    _sync(conn, tmp_path)
    approval.approve(conn, "demo-pret-caesar-wrap", "item")
    approval.approve(conn, "demo-deal-waitrose", "deal")
    assert not [r for r in db.fetch_approved_items(conn) if r["item_id"].startswith("demo-")]
    assert not [r for r in db.fetch_approved_deals(conn) if r["deal_id"].startswith("demo-")]
    assert not [r for r in db.fetch_items_for_shop(conn, "pret-tcr") if r["item_id"].startswith("demo-")]
    counts = export_snapshot(conn, tmp_path / "approved.json")
    exported = json.loads((tmp_path / "approved.json").read_text())
    assert not [i for i in exported["items"] if i["item_id"].startswith("demo-")]
    assert not [d for d in exported["deals"] if d["deal_id"].startswith("demo-")]


def test_seeded_tasks_point_at_real_shops_and_photo_types(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch)
    shops = {r["shop_id"] for r in db.fetch_all_shops(conn)}
    tasks = db.fetch_all_tasks(conn)
    assert len(tasks) >= 9
    assert {t["shop_id"] for t in tasks} >= {"waitrose-brunswick", "lidl-tcr", "ms-tcr", "pret-tcr"}
    for t in tasks:
        assert t["shop_id"] in shops and t["photo_type"] in ("general", "main", "snack", "drink")
        assert t["ask"] and t["needed"] and t["bonus_credits"] > 0
