"""
Fill a product's missing kcal / protein / ingredients / allergens by barcode.

Order:
  1. Barcode check against OUR data — another product with the same barcode whose
     value was read from its own label (any shop: same barcode = same product).
  2. Open Food Facts by barcode — for whatever step 1 couldn't fill.
  3. Open Food Facts by NAME — for every product still missing something, barcode or
     not. Strict match (see openfoodfacts.search_by_name); the source names the
     matched product. Results are cached in the off_name_cache table so a long bulk
     run can stop and resume without asking twice.

Only gaps are filled; label values always win. Diet flags and meats are never filled.
Every filled field is recorded in external_fields with its source, and the app shows
it next to an allergy warning. Allergens copied from our own data were read from a
printed label of the same product, so allergy filters trust them; allergens from Open
Food Facts can only mark a product unsafe (see optimiser.hard_filter). Runs only on import / "Read photos" / the admin
button — never on page render.
"""

from __future__ import annotations

import json
import sqlite3

import openfoodfacts
from openfoodfacts import normalise_barcode

FILLABLE = ("kcal", "protein_g", "ingredients_text", "allergens")
OUR_DATA = "same barcode, another photo"


def _empty(value) -> bool:
    return value in (None, "") or value == []


def _missing(fields: dict) -> list[str]:
    return [f for f in FILLABLE if _empty(fields.get(f))]


def from_our_data(conn: sqlite3.Connection, barcode: str, wanted: list[str]) -> dict:
    """Label-read values for this barcode from items we already hold (not rejected)."""
    found: dict = {}
    rows = conn.execute(
        "SELECT kcal, protein_g, ingredients_text, allergens, external_fields FROM items "
        "WHERE barcode = ? AND status != 'rejected' ORDER BY status = 'approved' DESC, last_seen DESC",
        (barcode,),
    ).fetchall()
    for row in rows:
        external = json.loads(row["external_fields"] or "{}")
        for f in wanted:
            value = json.loads(row[f] or "[]") if f == "allergens" else row[f]
            # Only copy values that were read from that item's own label, so
            # Open Food Facts data never gets passed on as if it were ours
            if f not in found and not _empty(value) and f not in external:
                found[f] = value
    return found


_CACHE_SCHEMA = """CREATE TABLE IF NOT EXISTS off_name_cache (
    name TEXT PRIMARY KEY, result TEXT, matched TEXT, checked_at TEXT NOT NULL)"""


def _name_lookup(conn: sqlite3.Connection | None, name: str) -> tuple[dict, str] | None:
    """search_by_name with a persistent cache (misses are cached too)."""
    key = " ".join(sorted(openfoodfacts.name_words(name)))
    if conn is not None:
        conn.execute(_CACHE_SCHEMA)
        row = conn.execute("SELECT result, matched FROM off_name_cache WHERE name = ?", (key,)).fetchone()
        if row is not None:
            return (json.loads(row[0]), row[1]) if row[0] else None
    found = openfoodfacts.search_by_name(name)
    if conn is not None:
        conn.execute(
            "INSERT OR REPLACE INTO off_name_cache (name, result, matched, checked_at) VALUES (?, ?, ?, datetime('now'))",
            (key, json.dumps(found[0]) if found else None, found[1] if found else None),
        )
        conn.commit()
    return found


def fill_missing(conn: sqlite3.Connection | None, fields: dict, use_openfoodfacts: bool = True,
                 use_name_search: bool = True) -> dict:
    """Copy of an extracted product with gaps filled; sources noted in external_fields."""
    barcode = normalise_barcode(fields.get("barcode"))
    wanted = _missing(fields)
    if not wanted or (barcode is None and not (use_openfoodfacts and use_name_search)):
        return fields

    out = {**fields, "barcode": barcode}
    sources = dict(out.get("external_fields") or {})

    if conn is not None and barcode is not None:
        for f, value in from_our_data(conn, barcode, wanted).items():
            out[f] = value
            sources[f] = OUR_DATA

    still = _missing(out)
    if still and use_openfoodfacts and barcode is not None:
        found = openfoodfacts.lookup(barcode) or {}
        for f in still:
            if not _empty(found.get(f)):
                out[f] = found[f]
                sources[f] = openfoodfacts.SOURCE

    still = _missing(out)
    if still and use_openfoodfacts and use_name_search and out.get("name"):
        match = _name_lookup(conn, out["name"])
        if match:
            found, label = match
            for f in still:
                if not _empty(found.get(f)):
                    out[f] = found[f]
                    sources[f] = f"{openfoodfacts.SOURCE} (name match: {label})"

    out["external_fields"] = sources
    return out


def fill_existing(conn: sqlite3.Connection, limit: int | None = None,
                  log=lambda message: None) -> tuple[int, int]:
    """
    Fill gaps on items already in the DB — every item, barcode or not.
    Name searches are rate-limited (~10/min), so a full run takes a while; cached
    names are instant, so re-running resumes. Returns (items checked, fields filled).
    """
    rows = conn.execute(
        "SELECT * FROM items WHERE status != 'rejected' AND source_image != 'fallback.jpg' "
        "AND (kcal IS NULL OR protein_g IS NULL OR ingredients_text IS NULL OR ingredients_text = '' "
        "OR allergens IS NULL OR allergens = '[]') ORDER BY status = 'approved' DESC, item_id"
        + (f" LIMIT {int(limit)}" if limit else "")
    ).fetchall()
    filled_total = 0
    for n, row in enumerate(rows, start=1):
        before = dict(row)
        before["external_fields"] = json.loads(before.get("external_fields") or "{}")
        before["allergens"] = json.loads(before.get("allergens") or "[]")
        after = fill_missing(conn, before)
        changed = [f for f in FILLABLE if _empty(before.get(f)) and not _empty(after.get(f))]
        if not changed:
            log(f"[{n}/{len(rows)}] {row['name']}: nothing found")
            continue
        log(f"[{n}/{len(rows)}] {row['name']}: filled {', '.join(changed)}")
        sets = ", ".join(f"{f} = ?" for f in changed)
        conn.execute(
            f"UPDATE items SET {sets}, external_fields = ? WHERE item_id = ?",
            [json.dumps(after[f]) if f == "allergens" else after[f] for f in changed]
            + [json.dumps(after["external_fields"]), row["item_id"]],
        )
        filled_total += len(changed)
    conn.commit()
    return len(rows), filled_total
