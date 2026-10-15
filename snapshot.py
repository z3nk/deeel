"""
Approved-data snapshot: how reviewed data reaches the deployed app.

The SQLite file is gitignored and Streamlit Cloud's disk doesn't persist, so:
  1. Review locally, then export:  python seed/load_seed.py --export
     (or the "Export approved data" button in the Review queue)
     → seed/approved.json  (approved real items + deals; placeholder rows excluded)
  2. Commit + push it.
  3. Every app instance syncs it on startup (db._auto_seed_items):
     - upserts the snapshot's items/deals as approved (ids are stable)
     - then prune_placeholders(): shops with approved real data lose their
       placeholder rows; shops with none keep them (any instance, local too)
     - removes approved rows that an earlier snapshot added but this one dropped
     - never touches anything else (e.g. student uploads on the deployed app)
     Re-syncs only when the file's content hash changes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).parent / "seed" / "approved.json"
_FALLBACK_IMAGE = "fallback.jpg"
_JSON_COLUMNS = {"diet_flags", "allergens", "meats", "external_fields"}

_META_SCHEMA = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _meta_get(conn, key: str) -> str | None:
    conn.execute(_META_SCHEMA)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(_META_SCHEMA)
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def prune_placeholders(conn: sqlite3.Connection) -> None:
    """Real data replaces placeholders shop by shop: drop fallback rows where approved real ones exist."""
    for table in ("items", "deals"):
        conn.execute(
            f"DELETE FROM {table} WHERE source_image = :fb AND shop_id IN "
            f"(SELECT shop_id FROM {table} WHERE status = 'approved' AND source_image != :fb)",
            {"fb": _FALLBACK_IMAGE},
        )
    conn.commit()


def meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    return _meta_get(conn, key)


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    _meta_set(conn, key, value)
    conn.commit()


def export_snapshot(conn: sqlite3.Connection, path: Path = SNAPSHOT_PATH) -> dict:
    """Write approved, non-placeholder items and deals to JSON. Returns counts."""
    items = []
    for row in conn.execute(
        "SELECT * FROM items WHERE status = 'approved' AND source_image != ? ORDER BY shop_id, category, name",
        (_FALLBACK_IMAGE,),
    ):
        d = dict(row)
        for col in _JSON_COLUMNS & d.keys():
            d[col] = json.loads(d[col]) if d[col] else ([] if col in ("diet_flags", "allergens") else None)
        items.append(d)
    deals = [dict(r) for r in conn.execute(
        "SELECT * FROM deals WHERE status = 'approved' AND source_image != ? ORDER BY shop_id, name",
        (_FALLBACK_IMAGE,),
    )]
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {"items": len(items), "deals": len(deals)},
        "items": items,
        "deals": deals,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    return payload["counts"]


def sync_snapshot(conn: sqlite3.Connection, path: Path = SNAPSHOT_PATH) -> bool:
    """Load the snapshot into this DB if it changed. Returns True if a snapshot is present."""
    if not path.exists():
        return False
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if _meta_get(conn, "snapshot_hash") == digest:
        return True

    data = json.loads(raw)
    items, deals = data.get("items", []), data.get("deals", [])
    item_cols, deal_cols = set(_columns(conn, "items")), set(_columns(conn, "deals"))

    # Drop approved rows an earlier snapshot added that this one no longer has
    new_item_ids = {i["item_id"] for i in items}
    new_deal_ids = {d["deal_id"] for d in deals}
    for table, id_col, key, keep in (("items", "item_id", "snapshot_item_ids", new_item_ids),
                                     ("deals", "deal_id", "snapshot_deal_ids", new_deal_ids)):
        for old_id in set(json.loads(_meta_get(conn, key) or "[]")) - keep:
            conn.execute(f"DELETE FROM {table} WHERE {id_col} = ? AND status = 'approved'", (old_id,))

    for table, rows, cols in (("items", items, item_cols), ("deals", deals, deal_cols)):
        for row in rows:
            record = {k: v for k, v in row.items() if k in cols}
            record["status"] = "approved"
            for col in _JSON_COLUMNS & record.keys():
                if record[col] is not None and not isinstance(record[col], str):
                    record[col] = json.dumps(record[col])
            names = ", ".join(record)
            marks = ", ".join(f":{k}" for k in record)
            conn.execute(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({marks})", record)

    _meta_set(conn, "snapshot_item_ids", json.dumps(sorted(new_item_ids)))
    _meta_set(conn, "snapshot_deal_ids", json.dumps(sorted(new_deal_ids)))
    _meta_set(conn, "snapshot_hash", digest)
    conn.commit()
    return True
