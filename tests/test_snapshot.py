"""Tests for snapshot.py — exporting approved data and loading it on another instance."""

import json
from pathlib import Path
from datetime import date

import pytest

import approval
import db
from extract import build_deal, build_item
from snapshot import export_snapshot, prune_placeholders, sync_snapshot


def _fresh(tmp_path, name, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / name)
    monkeypatch.setattr(db, "_conn", None)
    return db.get_connection()          # loads placeholders like a fresh deploy


def _approve_item(conn, name, shop="tesco-tcr", **extra):
    item = build_item({"name": name, "category": "main", "price_gbp": 3.5, "confidence": "high",
                       "allergens": ["milk"], **extra}, shop, f"{shop}/main/x.jpg", date(2026, 10, 15), "u-sam")
    data = item.model_dump(); data["last_seen"] = item.last_seen.isoformat()
    approval.approve(conn, approval.queue_item(conn, data), "item")
    return item.item_id


def test_export_then_load_on_a_fresh_deploy(tmp_path, monkeypatch):
    local = _fresh(tmp_path, "local.db", monkeypatch)
    _approve_item(local, "Real Wrap", meats=["chicken"], external_fields={"kcal": "Open Food Facts"}, kcal=480)
    approval.queue_item(local, {**build_item({"name": "Pending", "category": "main", "price_gbp": 2,
                                              "confidence": "high"}, "tesco-tcr", "tesco-tcr/main/y.jpg",
                                             date(2026, 10, 15), None).model_dump(), "last_seen": "2026-10-15"})
    deal = build_deal({"name": "Meal Deal", "price_gbp": 3.85}, "tesco-tcr", "tesco-tcr/general/d.jpg",
                      date(2026, 10, 15), None)
    approval.approve(local, approval.queue_deal(local, {**deal.model_dump(), "last_seen": "2026-10-15"}), "deal")
    path = tmp_path / "approved.json"
    counts = export_snapshot(local, path)
    assert counts == {"items": 1, "deals": 1}                    # pending + placeholders excluded
    local.close()

    cloud = _fresh(tmp_path, "cloud.db", monkeypatch)
    assert sync_snapshot(cloud, path)
    prune_placeholders(cloud)
    tesco = [tuple(r) for r in cloud.execute("SELECT name, status, meats, external_fields FROM items WHERE shop_id='tesco-tcr'")]
    assert tesco == [("Real Wrap", "approved", '["chicken"]', '{"kcal": "Open Food Facts"}')]  # placeholders gone
    assert [tuple(r) for r in cloud.execute("SELECT price_gbp FROM deals WHERE shop_id='tesco-tcr'")] == [(3.85,)]
    # shops without real data keep their placeholders
    assert cloud.execute("SELECT COUNT(*) FROM items WHERE shop_id='pret-tcr'").fetchone()[0] > 0
    cloud.close()


def test_resync_only_on_change_and_drops_removed_rows(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, "c.db", monkeypatch)
    path = tmp_path / "approved.json"
    item = {"item_id": "real-1", "shop_id": "ms-tcr", "name": "Real", "category": "main", "price_gbp": 4,
            "temperature": "cold", "diet_flags": [], "allergens": [], "source_image": "ms-tcr/main/a.jpg",
            "source_text": "", "last_seen": "2026-10-15", "submitted_via": "seed", "status": "approved",
            "confidence": "high", "needs_review": 0}
    path.write_text(json.dumps({"items": [item], "deals": []}))
    assert sync_snapshot(conn, path)
    conn.execute("UPDATE items SET name='edited' WHERE item_id='real-1'"); conn.commit()
    sync_snapshot(conn, path)                                     # unchanged file → no re-apply
    assert conn.execute("SELECT name FROM items WHERE item_id='real-1'").fetchone()[0] == "edited"

    path.write_text(json.dumps({"items": [], "deals": []}))
    sync_snapshot(conn, path)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE item_id='real-1'").fetchone()[0] == 0


def test_no_snapshot_file_is_fine(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, "c.db", monkeypatch)
    assert sync_snapshot(conn, tmp_path / "missing.json") is False
    import importlib.util
    spec = importlib.util.spec_from_file_location("load_seed", Path(__file__).parent.parent / "seed" / "load_seed.py")
    seed = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == len(seed.FALLBACK_ITEMS)   # placeholders loaded
