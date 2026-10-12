"""
Credit ledger: earning rules, daily cap, reputation multiplier, rewards redemption.

Earning rules (from PLAN.md):
- 10 credits per approved item photo; 20 for a meal deal sign
- Freshness bonus: 2x if the shop's previous record for that item is > 14 days old
- Coverage bonus: +10 for the first photo of a shop/category with no current data
- Confirmation: +5 if a new photo confirms an existing price (raises confidence)
- Cap: 100 credits per user per day
- Correction reverses credits if a record is later proven wrong
- Reputation multiplier: 1.0–1.5, applied to base award
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from db import get_user_credit_balance

# ---------------------------------------------------------------------------
# Constants (tune on seed data)
# ---------------------------------------------------------------------------

BASE_ITEM = 10
BASE_DEAL = 20
FRESHNESS_MULTIPLIER = 2
COVERAGE_BONUS = 10
CONFIRMATION_BONUS = 5
DAILY_CAP = 100
STALE_DAYS = 14


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today_credits(conn: sqlite3.Connection, user_id: str) -> int:
    """Credits earned today (excludes spend and reversals)."""
    today = date.today().isoformat()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(credits), 0)
        FROM credit_events
        WHERE user_id = ?
          AND type = 'earn'
          AND DATE(created_at) = ?
        """,
        (user_id, today),
    ).fetchone()
    return int(row[0])


def _existing_record(
    conn: sqlite3.Connection, shop_id: str, name: str, category: str
) -> sqlite3.Row | None:
    """Return the most recent approved item matching shop + name + category."""
    return conn.execute(
        """
        SELECT * FROM items
        WHERE shop_id = ? AND name = ? AND category = ? AND status = 'approved'
        ORDER BY last_seen DESC
        LIMIT 1
        """,
        (shop_id, name, category),
    ).fetchone()


def _has_category_data(conn: sqlite3.Connection, shop_id: str, category: str) -> bool:
    """True if the shop already has at least one approved item in this category."""
    row = conn.execute(
        "SELECT 1 FROM items WHERE shop_id = ? AND category = ? AND status = 'approved' LIMIT 1",
        (shop_id, category),
    ).fetchone()
    return row is not None


def _user_reputation(conn: sqlite3.Connection, user_id: str) -> float:
    row = conn.execute(
        "SELECT reputation FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    return float(row["reputation"]) if row else 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_credits(
    conn: sqlite3.Connection,
    item_id: str,
    user_id: str,
    record_type: Literal["item", "deal"] = "item",
) -> int:
    """
    Calculate how many credits to award for an approved item or deal.
    Returns 0 if the user has already hit the daily cap.
    Does NOT write to the database — call apply_credits() to persist.
    """
    # Fetch the approved item/deal
    if record_type == "item":
        row = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM deals WHERE deal_id = ?", (item_id,)).fetchone()

    if row is None:
        return 0

    # Check daily cap
    earned_today = _today_credits(conn, user_id)
    if earned_today >= DAILY_CAP:
        return 0

    reputation = _user_reputation(conn, user_id)
    base = BASE_DEAL if record_type == "deal" else BASE_ITEM
    credits = base

    if record_type == "item":
        existing = _existing_record(conn, row["shop_id"], row["name"], row["category"])

        if existing:
            # Freshness bonus: previous record is stale
            prev_date = date.fromisoformat(existing["last_seen"])
            if (date.today() - prev_date).days > STALE_DAYS:
                credits *= FRESHNESS_MULTIPLIER

            # Confirmation bonus: same price as existing record
            if abs(float(existing["price_gbp"]) - float(row["price_gbp"])) < 0.01:
                credits += CONFIRMATION_BONUS
        else:
            # Coverage bonus: first record for this shop/category
            if not _has_category_data(conn, row["shop_id"], row["category"]):
                credits += COVERAGE_BONUS

    # Apply reputation multiplier and enforce daily cap
    credits = int(credits * reputation)
    remaining_cap = DAILY_CAP - earned_today
    return min(credits, remaining_cap)


def apply_credits(
    conn: sqlite3.Connection,
    item_id: str,
    user_id: str,
    record_type: Literal["item", "deal"] = "item",
) -> int:
    """
    Calculate and write a credit earn event to the ledger.
    Returns the number of credits awarded (0 if capped or record not found).
    """
    credits = calculate_credits(conn, item_id, user_id, record_type)
    if credits == 0:
        return 0

    reason = "approved_deal" if record_type == "deal" else "approved_item"

    # Freshness bonus needs its own event so it's traceable
    row = conn.execute(
        "SELECT * FROM items WHERE item_id = ?" if record_type == "item"
        else "SELECT * FROM deals WHERE deal_id = ?",
        (item_id,),
    ).fetchone()

    if row and record_type == "item":
        existing = _existing_record(conn, row["shop_id"], row["name"], row["category"])
        if existing:
            prev_date = date.fromisoformat(existing["last_seen"])
            if (date.today() - prev_date).days > STALE_DAYS:
                reason = "stale_bonus"

    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO credit_events (event_id, user_id, type, credits, reason, ref_id, created_at)
        VALUES (?, ?, 'earn', ?, ?, ?, ?)
        """,
        (event_id, user_id, credits, reason, item_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return credits


def reverse_credits(
    conn: sqlite3.Connection,
    item_id: str,
    user_id: str,
) -> int:
    """
    Reverse all credits previously earned for a specific item (on rejection
    after approval, or later correction). Returns the amount reversed (positive).
    """
    rows = conn.execute(
        """
        SELECT event_id, credits FROM credit_events
        WHERE user_id = ? AND ref_id = ? AND type = 'earn'
        """,
        (user_id, item_id),
    ).fetchall()

    total_reversed = sum(r["credits"] for r in rows)
    if total_reversed == 0:
        return 0

    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO credit_events (event_id, user_id, type, credits, reason, ref_id, created_at)
        VALUES (?, ?, 'reversal', ?, 'reversal', ?, ?)
        """,
        (event_id, user_id, -total_reversed, item_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return total_reversed


def redeem_reward(
    conn: sqlite3.Connection,
    user_id: str,
    reward_id: str,
) -> str | None:
    """
    Spend credits for a reward. Returns the redeemed code, or None if:
    - insufficient balance
    - no codes remaining
    - reward not found or expired
    """
    reward = conn.execute(
        "SELECT * FROM rewards WHERE reward_id = ?", (reward_id,)
    ).fetchone()

    if reward is None:
        return None
    if reward["codes_remaining"] <= 0:
        return None
    if reward["expires"] and date.fromisoformat(reward["expires"]) < date.today():
        return None

    balance = get_user_credit_balance(conn, user_id)
    if balance < reward["cost_credits"]:
        return None

    # Generate a mock code (replace with real code pool post-hackathon)
    code = f"DEMO-{reward_id.upper()[:6]}-{uuid.uuid4().hex[:6].upper()}"

    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO credit_events (event_id, user_id, type, credits, reason, ref_id, created_at)
        VALUES (?, ?, 'spend', ?, 'reward_redeemed', ?, ?)
        """,
        (event_id, user_id, -reward["cost_credits"], reward_id, datetime.utcnow().isoformat()),
    )
    conn.execute(
        "UPDATE rewards SET codes_remaining = codes_remaining - 1 WHERE reward_id = ?",
        (reward_id,),
    )
    conn.execute(
        """
        INSERT INTO reward_redemptions (redemption_id, reward_id, user_id, code, redeemed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), reward_id, user_id, code, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return code


def get_credit_history(
    conn: sqlite3.Connection, user_id: str, limit: int = 20
) -> list[sqlite3.Row]:
    """Return the most recent credit events for a user, newest first."""
    return conn.execute(
        """
        SELECT * FROM credit_events
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def get_pending_credits(conn: sqlite3.Connection, user_id: str) -> int:
    """
    Return the total credits a user would earn if all their pending
    submissions were approved today. Used for the 'awaiting review' display.
    This is an estimate — actual amount depends on approval timing.
    """
    pending_items = conn.execute(
        "SELECT item_id FROM items WHERE submitted_by = ? AND status = 'pending'",
        (user_id,),
    ).fetchall()

    total = 0
    for row in pending_items:
        total += calculate_credits(conn, row["item_id"], user_id, "item")
    return total
