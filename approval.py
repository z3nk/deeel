"""
Approval queue: pending → approved / rejected flow.

- queue_item / queue_deal: save a new record with status='pending'
- approve / reject: flip status, trigger credit award or reversal
- Image deduplication via imagehash (rejects recycled photos)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import imagehash
from PIL import Image

from ledger import apply_credits, reverse_credits

# ---------------------------------------------------------------------------
# Image deduplication
# ---------------------------------------------------------------------------

def _compute_hash(image_path: Path) -> str:
    img = Image.open(image_path)
    return str(imagehash.phash(img))


def is_duplicate(conn: sqlite3.Connection, image_path: Path) -> bool:
    """
    Return True if an image with the same perceptual hash is already in the DB.
    Threshold: hash distance ≤ 8 is considered a duplicate.
    """
    new_hash = _compute_hash(image_path)
    existing = conn.execute(
        "SELECT source_image FROM items UNION SELECT source_image FROM deals"
    ).fetchall()

    for row in existing:
        stored_path = Path("uploads") / row[0]
        if not stored_path.exists():
            continue
        try:
            stored_hash = _compute_hash(stored_path)
            if imagehash.hex_to_hash(new_hash) - imagehash.hex_to_hash(stored_hash) <= 8:
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Queue new submissions
# ---------------------------------------------------------------------------

def queue_item(
    conn: sqlite3.Connection,
    item_data: dict,
) -> str:
    """
    Insert a new item with status='pending'. item_data must match the items
    table schema. Returns the item_id.
    """
    item_id = item_data.get("item_id") or str(uuid.uuid4())[:8]
    conn.execute(
        """
        INSERT INTO items (
            item_id, shop_id, name, category, price_gbp, loyalty_price_gbp,
            meal_deal_eligible, temperature, diet_flags, allergens,
            ingredients_text, meats, kcal, protein_g,
            premium_range, quality_rating, source_image,
            source_text, last_seen, submitted_via, submitted_by,
            status, confidence, needs_review
        ) VALUES (
            :item_id, :shop_id, :name, :category, :price_gbp, :loyalty_price_gbp,
            :meal_deal_eligible, :temperature, :diet_flags, :allergens,
            :ingredients_text, :meats, :kcal, :protein_g,
            :premium_range, :quality_rating, :source_image,
            :source_text, :last_seen, :submitted_via, :submitted_by,
            'pending', :confidence, :needs_review
        )
        """,
        {
            **item_data,
            "item_id": item_id,
            "diet_flags": json.dumps(item_data.get("diet_flags", [])),
            "allergens": json.dumps(item_data.get("allergens", [])),
            "meats": (
                None if item_data.get("meats") is None
                else json.dumps(item_data["meats"])
            ),
            "kcal": item_data.get("kcal"),
            "protein_g": item_data.get("protein_g"),
        },
    )
    conn.commit()
    return item_id


def queue_deal(
    conn: sqlite3.Connection,
    deal_data: dict,
) -> str:
    """
    Insert a new deal with status='pending'. Returns the deal_id.
    """
    deal_id = deal_data.get("deal_id") or str(uuid.uuid4())[:8]
    conn.execute(
        """
        INSERT INTO deals (
            deal_id, shop_id, name, price_gbp, loyalty_price_gbp,
            loyalty_scheme, source_image, last_seen, submitted_by, status
        ) VALUES (
            :deal_id, :shop_id, :name, :price_gbp, :loyalty_price_gbp,
            :loyalty_scheme, :source_image, :last_seen, :submitted_by, 'pending'
        )
        """,
        {**deal_data, "deal_id": deal_id},
    )
    conn.commit()
    return deal_id


# ---------------------------------------------------------------------------
# Approve / reject
# ---------------------------------------------------------------------------

def approve(
    conn: sqlite3.Connection,
    record_id: str,
    record_type: Literal["item", "deal"] = "item",
) -> int:
    """
    Flip status to 'approved' and pay credits to the submitter.
    Returns credits awarded (0 if no submitter or already approved).
    """
    table = "items" if record_type == "item" else "deals"
    id_col = "item_id" if record_type == "item" else "deal_id"

    row = conn.execute(
        f"SELECT * FROM {table} WHERE {id_col} = ?", (record_id,)
    ).fetchone()

    if row is None or row["status"] == "approved":
        return 0

    conn.execute(
        f"UPDATE {table} SET status = 'approved' WHERE {id_col} = ?",
        (record_id,),
    )
    conn.commit()

    submitter = row["submitted_by"]
    if not submitter:
        return 0

    # credit_events.user_id is a foreign key; make sure the submitter exists
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, handle) VALUES (?, ?)",
        (submitter, submitter),
    )
    return apply_credits(conn, record_id, submitter, record_type)


def reject(
    conn: sqlite3.Connection,
    record_id: str,
    record_type: Literal["item", "deal"] = "item",
    reason: str = "",
) -> int:
    """
    Flip status to 'rejected' and reverse any credits already paid.
    Returns the number of credits reversed (0 if none were paid).
    """
    table = "items" if record_type == "item" else "deals"
    id_col = "item_id" if record_type == "item" else "deal_id"

    row = conn.execute(
        f"SELECT * FROM {table} WHERE {id_col} = ?", (record_id,)
    ).fetchone()

    if row is None:
        return 0

    conn.execute(
        f"UPDATE {table} SET status = 'rejected' WHERE {id_col} = ?",
        (record_id,),
    )
    conn.commit()

    submitter = row["submitted_by"]
    if not submitter or row["status"] != "approved":
        return 0

    return reverse_credits(conn, record_id, submitter)


# ---------------------------------------------------------------------------
# Queue queries (for the review screen)
# ---------------------------------------------------------------------------

def get_pending_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE status = 'pending' ORDER BY last_seen DESC"
    ).fetchall()


def get_pending_deals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deals WHERE status = 'pending' ORDER BY last_seen DESC"
    ).fetchall()


def get_user_submissions(
    conn: sqlite3.Connection, user_id: str
) -> list[sqlite3.Row]:
    """All item submissions by a user, newest first."""
    return conn.execute(
        """
        SELECT *, 'item' as record_type FROM items WHERE submitted_by = ?
        UNION ALL
        SELECT deal_id as item_id, shop_id, name, price_gbp, loyalty_price_gbp,
               NULL, NULL, NULL, '[]', '[]', NULL, NULL, NULL,
               source_image, '' as source_text, last_seen, 'upload', submitted_by,
               status, 'high', 0, 'deal' as record_type
        FROM deals WHERE submitted_by = ?
        ORDER BY last_seen DESC
        """,
        (user_id, user_id),
    ).fetchall()
