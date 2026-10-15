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
    price_gbp           REAL,           -- NULL = deal-only (only a meal deal price shown)
    loyalty_price_gbp   REAL,
    meal_deal_eligible  INTEGER,        -- 1/0/NULL
    temperature         TEXT NOT NULL,
    diet_flags          TEXT NOT NULL DEFAULT '[]',   -- JSON array
    allergens           TEXT NOT NULL DEFAULT '[]',   -- JSON array
    ingredients_text    TEXT,
    meats               TEXT,           -- JSON array or NULL (unknown)
    kcal                REAL,           -- per pack, NULL = not on label
    protein_g           REAL,           -- per pack, NULL = not on label
    barcode             TEXT,           -- EAN/UPC digits, NULL = not read
    external_fields     TEXT,           -- JSON {field: source} for values not from this label
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

CREATE TABLE IF NOT EXISTS tasks (
    task_id       TEXT PRIMARY KEY,
    shop_id       TEXT NOT NULL REFERENCES shops(shop_id),
    item_name     TEXT NOT NULL,        -- what to photograph
    needed        TEXT NOT NULL,        -- e.g. "price + allergens"
    ask           TEXT NOT NULL,        -- instruction shown to the user
    photo_type    TEXT NOT NULL DEFAULT 'main',  -- main / snack / drink / general
    bonus_credits INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS task_completions (
    completion_id TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL REFERENCES tasks(task_id),
    user_id       TEXT NOT NULL,
    item_id       TEXT,                 -- item submitted for this task (nullable)
    completed_at  TEXT NOT NULL,
    UNIQUE(task_id, user_id)            -- one completion per user per task
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_items_shop     ON items(shop_id);
CREATE INDEX IF NOT EXISTS idx_items_status   ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_last_seen ON items(last_seen);
CREATE INDEX IF NOT EXISTS idx_deals_shop     ON deals(shop_id);
CREATE INDEX IF NOT EXISTS idx_credits_user   ON credit_events(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_shop     ON tasks(shop_id);
CREATE INDEX IF NOT EXISTS idx_completions_user ON task_completions(user_id);
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
        # Warren Street branch. Coordinates + walking time are estimates — confirm on the walk.
        "shop_id": "sainsburys-warren-st",
        "chain": "sainsburys",
        "name": "Sainsbury's Local (Warren Street)",
        "address": "21 Hampstead Road, London NW1",
        "walking_minutes": 5.0,
        "last_verified": "2026-10-15",
        "lat": 51.5261,
        "lng": -0.1387,
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
# Seed tasks (placeholder — swap for real tasks before the demo walk)
# ---------------------------------------------------------------------------

_SEED_TASKS = [
    {
        "task_id": "task-tesco-deal-sign",
        "shop_id": "tesco-tcr",
        "item_name": "Meal deal price board",
        "needed": "current deal price",
        "photo_type": "general",
        "ask": "Photograph the full meal deal sign so the price is sharp and readable.",
        "bonus_credits": 15,
    },
    {
        "task_id": "task-pret-chicken-wrap",
        "shop_id": "pret-tcr",
        "item_name": "Chicken Caesar Wrap",
        "needed": "price + allergens",
        "photo_type": "main",
        "ask": "Get the front label in frame. Make sure the allergen box is visible.",
        "bonus_credits": 10,
    },
    {
        "task_id": "task-ms-percy-pigs",
        "shop_id": "ms-tcr",
        "item_name": "Percy Pig sweets",
        "needed": "price + meal deal eligibility",
        "photo_type": "snack",
        "ask": "Photograph the shelf edge label. Check if there's a meal deal sticker.",
        "bonus_credits": 10,
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
    _migrate(conn)
    _migrate_nullable_price(conn)
    _migrate_tasks(conn)
    _seed_shops(conn)
    _rename_shops(conn)
    _seed_rewards(conn)
    _seed_tasks(conn)
    conn.commit()
    _auto_seed_items(conn)


_ITEM_COLUMNS_ADDED = {"meats": "TEXT", "kcal": "REAL", "protein_g": "REAL",
                       "barcode": "TEXT", "external_fields": "TEXT"}

# Bump when FALLBACK_ITEMS/FALLBACK_* data in seed/load_seed.py changes, so existing
# databases (including the deployed one) drop and reload their fallback rows.
FALLBACK_DATA_VERSION = 2


def _migrate_nullable_price(conn: sqlite3.Connection) -> None:
    """items.price_gbp used to be NOT NULL. SQLite can't drop that in place, so rebuild."""
    info = {r["name"]: r for r in conn.execute("PRAGMA table_info(items)")}
    if not info["price_gbp"]["notnull"]:
        return
    import re
    ddl = re.search(r"CREATE TABLE IF NOT EXISTS items \((.*?)\n\);", _SCHEMA, re.S).group(1)
    cols = ", ".join(info)
    conn.executescript(f"""
        CREATE TABLE items__new ({ddl}
        );
        INSERT INTO items__new ({cols}) SELECT {cols} FROM items;
        DROP TABLE items;
        ALTER TABLE items__new RENAME TO items;
    """)
    conn.executescript(_SCHEMA)   # recreate indexes
    conn.commit()


def _migrate_tasks(conn: sqlite3.Connection) -> None:
    """Add tasks.photo_type to older DBs and fill it for the seeded tasks."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    if "photo_type" in existing:
        return
    conn.execute("ALTER TABLE tasks ADD COLUMN photo_type TEXT NOT NULL DEFAULT 'main'")
    conn.executemany(
        "UPDATE tasks SET photo_type = :photo_type WHERE task_id = :task_id",
        _SEED_TASKS,
    )
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """
    Add columns introduced after a DB was first created.
    If any were missing, or the fallback data version changed, drop fallback seed rows so _auto_seed_items reloads them
    with the new fields filled in. Real (photo/upload) records are kept.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    missing = {c: t for c, t in _ITEM_COLUMNS_ADDED.items() if c not in existing}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if not missing and version >= FALLBACK_DATA_VERSION:
        return
    for col, col_type in missing.items():
        conn.execute(f"ALTER TABLE items ADD COLUMN {col} {col_type}")
    conn.execute(f"PRAGMA user_version = {FALLBACK_DATA_VERSION}")
    # _auto_seed_items reloads placeholders when this marker is missing
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("DELETE FROM meta WHERE key = 'fallback_version'")
    conn.commit()


def _auto_seed_items(conn: sqlite3.Connection) -> None:
    """
    1. Placeholder (fallback) data, loaded once per FALLBACK_DATA_VERSION, so every
       shop shows something on Streamlit Cloud without a manual seed step.
    2. The approved-data snapshot (seed/approved.json), if present — see snapshot.py.
    3. Placeholders removed for shops that now have approved real data.
    """
    from snapshot import meta_get, meta_set, prune_placeholders, sync_snapshot

    if meta_get(conn, "fallback_version") != str(FALLBACK_DATA_VERSION):
        conn.execute("DELETE FROM items WHERE source_image = 'fallback.jpg'")
        conn.execute("DELETE FROM deals WHERE source_image = 'fallback.jpg'")
        conn.commit()
        _load_fallback(conn)
        meta_set(conn, "fallback_version", str(FALLBACK_DATA_VERSION))

    sync_snapshot(conn)
    prune_placeholders(conn)


def _load_fallback(conn: sqlite3.Connection) -> None:
    # Load in-process on this connection. Running load_seed.py as a subprocess
    # recursed forever: its own get_connection() saw an empty DB and spawned again.
    import importlib.util

    seed_script = Path(__file__).parent / "seed" / "load_seed.py"
    if seed_script.exists():
        spec = importlib.util.spec_from_file_location("load_seed", seed_script)
        load_seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load_seed)
        load_seed.load_fallback(conn)


# Old shop_id → new shop_id. Rows in items/deals/tasks/uploads are moved across.
_RENAMED_SHOPS = {"sainsburys-tcr": "sainsburys-warren-st"}


def _rename_shops(conn: sqlite3.Connection) -> None:
    """Run after _seed_shops (the new shop row must exist for the foreign keys)."""
    for old, new in _RENAMED_SHOPS.items():
        if conn.execute("SELECT 1 FROM shops WHERE shop_id = ?", (old,)).fetchone() is None:
            continue
        for table in ("items", "deals", "tasks"):
            conn.execute(f"UPDATE {table} SET shop_id = ? WHERE shop_id = ?", (new, old))
        for table in ("items", "deals"):
            conn.execute(
                f"UPDATE {table} SET source_image = ? || substr(source_image, ?) "
                f"WHERE source_image LIKE ?",
                (new + "/", len(old) + 2, old + "/%"),
            )
        conn.execute("DELETE FROM shops WHERE shop_id = ?", (old,))
        old_dir = Path(__file__).parent / "uploads" / old
        new_dir = Path(__file__).parent / "uploads" / new
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)
    conn.commit()


def _seed_shops(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO shops
            (shop_id, chain, name, address, walking_minutes, last_verified, lat, lng)
        VALUES
            (:shop_id, :chain, :name, :address, :walking_minutes, :last_verified, :lat, :lng)
        ON CONFLICT(shop_id) DO UPDATE SET
            chain = excluded.chain, name = excluded.name, address = excluded.address,
            walking_minutes = excluded.walking_minutes, last_verified = excluded.last_verified,
            lat = excluded.lat, lng = excluded.lng
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


def _seed_tasks(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO tasks
            (task_id, shop_id, item_name, needed, ask, photo_type, bonus_credits)
        VALUES
            (:task_id, :shop_id, :item_name, :needed, :ask, :photo_type, :bonus_credits)
        """,
        _SEED_TASKS,
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


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def fetch_all_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all tasks ordered by bonus_credits descending."""
    return conn.execute(
        "SELECT * FROM tasks ORDER BY bonus_credits DESC"
    ).fetchall()


def get_completed_task_ids(conn: sqlite3.Connection, user_id: str) -> set[str]:
    """Return the set of task_ids this user has already completed."""
    rows = conn.execute(
        "SELECT task_id FROM task_completions WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r["task_id"] for r in rows}


def complete_task(
    conn: sqlite3.Connection,
    task_id: str,
    user_id: str,
    item_id: str | None = None,
) -> bool:
    """
    Mark a task complete for a user. No-ops if already completed (UNIQUE constraint).
    Returns True if a new completion was inserted, False if already done.
    """
    import uuid
    from datetime import datetime

    try:
        conn.execute(
            """
            INSERT INTO task_completions (completion_id, task_id, user_id, item_id, completed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), task_id, user_id, item_id, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return True
    except Exception:
        return False
