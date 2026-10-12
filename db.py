"""
SQLite schema, indexes, and a single cached connection.
Open this once at app startup via get_connection(); never open it per-request.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "meal_deal.db"

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS shops (
    shop_id          TEXT PRIMARY KEY,
    chain            TEXT NOT NULL,
    name             TEXT NOT NULL,
    address          TEXT NOT NULL,
    walking_minutes  REAL NOT NULL,
    last_verified    TEXT NOT NULL,   -- ISO date
    lat              REAL NOT NULL,
    lng              REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    deal_id             TEXT PRIMARY KEY,
    shop_id             TEXT NOT NULL REFERENCES shops(shop_id),
    name                TEXT NOT NULL,
    price_gbp           REAL NOT NULL,
    loyalty_price_gbp   REAL,
    loyalty_scheme      TEXT,
    source_image        TEXT NOT NULL,
    last_seen           TEXT NOT NULL,  -- ISO date
    submitted_by        TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS items (
    item_id             TEXT PRIMARY KEY,
    shop_id             TEXT NOT NULL REFERENCES shops(shop_id),
    name                TEXT NOT NULL,
    category            TEXT NOT NULL,
    price_gbp           REAL NOT NULL,
    loyalty_price_gbp   REAL,
    meal_deal_eligible  INTEGER,        -- 1/0/NULL
    temperature         TEXT NOT NULL,
    diet_flags          TEXT NOT NULL DEFAULT '[]',   -- JSON array
    allergens           TEXT NOT NULL DEFAULT '[]',   -- JSON array
    ingredients_text    TEXT,
    premium_range       INTEGER,        -- 1/0/NULL
    quality_rating      REAL,
    source_image        TEXT NOT NULL,
    source_text         TEXT NOT NULL,
    last_seen           TEXT NOT NULL,
    submitted_via       TEXT NOT NULL,
    submitted_by        TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    confidence          TEXT NOT NULL DEFAULT 'high',
    needs_review        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    user_id     TEXT PRIMARY KEY,
    handle      TEXT NOT NULL UNIQUE,
    reputation  REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS credit_events (
    event_id    TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    type        TEXT NOT NULL,
    credits     INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    ref_id      TEXT NOT NULL,
    created_at  TEXT NOT NULL   -- ISO datetime
);

CREATE TABLE IF NOT EXISTS rewards (
    reward_id       TEXT PRIMARY KEY,
    sponsor         TEXT NOT NULL,
    title           TEXT NOT NULL,
    cost_credits    INTEGER NOT NULL,
    codes_remaining INTEGER NOT NULL DEFAULT 0,
    expires         TEXT            -- ISO date or NULL
);

CREATE TABLE IF NOT EXISTS reward_redemptions (
    redemption_id   TEXT PRIMARY KEY,
    reward_id       TEXT NOT NULL REFERENCES rewards(reward_id),
    user_id         TEXT NOT NULL REFERENCES users(user_id),
    code            TEXT NOT NULL,
    redeemed_at     TEXT NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_items_shop     ON items(shop_id);
CREATE INDEX IF NOT EXISTS idx_items_status   ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_last_seen ON items(last_seen);
CREATE INDEX IF NOT EXISTS idx_deals_shop     ON deals(shop_id);
CREATE INDEX IF NOT EXISTS idx_credits_user   ON credit_events(user_id);
"""

# ---------------------------------------------------------------------------
# Seed shops
# Coordinates are approximate; confirm on the seed walk.
# Walking minutes are placeholder estimates; measure by hand from Main Quad.
# ---------------------------------------------------------------------------

_SEED_SHOPS = [
    {
        "shop_id": "tesco-tcr",
        "chain": "tesco",
        "name": "Tesco Express",
        "address": "124-125 Tottenham Court Road, London W1T 5AJ",
        "walking_minutes": 4.0,
        "last_verified": "2026-10-12",
        "lat": 51.5226,
        "lng": -0.1349,
    },
    {
        "shop_id": "lidl-tcr",
        "chain": "lidl",
        "name": "Lidl",
        "address": "145 Tottenham Court Road, London W1T 7NE",
        "walking_minutes": 5.0,
        "last_verified": "2026-10-12",
        "lat": 51.5231,
        "lng": -0.1349,
    },
    {
        "shop_id": "ms-tcr",
        "chain": "marks-and-spencer",
        "name": "M&S Food",
        "address": "15-17 Tottenham Court Road, London W1T 1BJ",
        "walking_minutes": 3.0,
        "last_verified": "2026-10-12",
        "lat": 51.5194,
        "lng": -0.1353,
    },
    {
        "shop_id": "sainsburys-tcr",
        "chain": "sainsburys",
        "name": "Sainsbury's Local",
        "address": "Tottenham Court Road, London (confirm address on seed walk)",
        "walking_minutes": 6.0,
        "last_verified": "2026-10-12",
        "lat": 51.5215,
        "lng": -0.1351,
    },
    {
        "shop_id": "waitrose-brunswick",
        "chain": "waitrose",
        "name": "Waitrose",
        "address": "The Brunswick Centre, 23-39 Brunswick Square, London WC1N 1AF",
        "walking_minutes": 10.0,
        "last_verified": "2026-10-12",
        "lat": 51.5236,
        "lng": -0.1218,
    },
    {
        "shop_id": "pret-tcr",
        "chain": "pret",
        "name": "Pret A Manger",
        "address": "Tottenham Court Road, London (confirm address on seed walk)",
        "walking_minutes": 7.0,
        "last_verified": "2026-10-12",
        "lat": 51.5220,
        "lng": -0.1350,
    },
]

# ---------------------------------------------------------------------------
# Seed rewards (mocked for hackathon — say so in the demo)
# ---------------------------------------------------------------------------

_SEED_REWARDS = [
    {
        "reward_id": "reward-coffee",
        "sponsor": "Campus Coffee Co. (placeholder)",
        "title": "Free small coffee",
        "cost_credits": 50,
        "codes_remaining": 10,
        "expires": None,
    },
    {
        "reward_id": "reward-lunch",
        "sponsor": "UCL Union (placeholder)",
        "title": "£1 off your next lunch",
        "cost_credits": 30,
        "codes_remaining": 20,
        "expires": None,
    },
]


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """
    Return the single shared SQLite connection.
    Creates and initialises the database on first call.
    Call this once at app startup and reuse the returned object.
    """
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_db(_conn)
    return _conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    _seed_shops(conn)
    _seed_rewards(conn)
    conn.commit()


def _seed_shops(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO shops
            (shop_id, chain, name, address, walking_minutes, last_verified, lat, lng)
        VALUES
            (:shop_id, :chain, :name, :address, :walking_minutes, :last_verified, :lat, :lng)
        """,
        _SEED_SHOPS,
    )


def _seed_rewards(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO rewards
            (reward_id, sponsor, title, cost_credits, codes_remaining, expires)
        VALUES
            (:reward_id, :sponsor, :title, :cost_credits, :codes_remaining, :expires)
        """,
        _SEED_REWARDS,
    )


# ---------------------------------------------------------------------------
# Helpers used by other modules
# ---------------------------------------------------------------------------

def fetch_all_shops(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM shops").fetchall()


def fetch_approved_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE status = 'approved'"
    ).fetchall()


def fetch_items_for_shop(conn: sqlite3.Connection, shop_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE shop_id = ? AND status IN ('approved', 'pending')",
        (shop_id,),
    ).fetchall()


def fetch_approved_deals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deals WHERE status = 'approved'"
    ).fetchall()


def fetch_pending_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE status = 'pending'"
    ).fetchall()


def fetch_pending_deals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deals WHERE status = 'pending'"
    ).fetchall()


def get_user_by_handle(conn: sqlite3.Connection, handle: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE handle = ?", (handle,)
    ).fetchone()


def upsert_user(conn: sqlite3.Connection, user_id: str, handle: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, handle) VALUES (?, ?)",
        (user_id, handle),
    )
    conn.commit()


def get_user_credit_balance(conn: sqlite3.Connection, user_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(credits), 0) FROM credit_events WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row[0])
