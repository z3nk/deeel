"""
Fill a product's missing kcal / protein / ingredients by barcode.

Order:
  1. Barcode check against OUR data — another product with the same barcode whose
     value was read from its own label (any shop: same barcode = same product).
  2. Open Food Facts — only for whatever step 1 couldn't fill.

Only gaps are filled; label values always win. Allergens, diet flags and meats are
never filled (label-only). Every filled field is recorded in external_fields with
its source, and the app shows it. Runs only on import / "Read photos" / the admin
button — never on page render.
"""

from __future__ import annotations

import json
import sqlite3

import openfoodfacts
from openfoodfacts import normalise_barcode

FILLABLE = ("kcal", "protein_g", "ingredients_text")
OUR_DATA = "same barcode, another photo"


def _missing(fields: dict) -> list[str]:
    return [f for f in FILLABLE if fields.get(f) in (None, "")]


def from_our_data(conn: sqlite3.Connection, barcode: str, wanted: list[str]) -> dict:
    """Label-read values for this barcode from items we already hold (not rejected)."""
    found: dict = {}
    rows = conn.execute(
        "SELECT kcal, protein_g, ingredients_text, external_fields FROM items "
        "WHERE barcode = ? AND status != 'rejected' ORDER BY status = 'approved' DESC, last_seen DESC",
        (barcode,),
    ).fetchall()
    for row in rows:
        external = json.loads(row["external_fields"] or "{}")
        for f in wanted:
            # Only copy values that were read from that item's own label, so
            # Open Food Facts data never gets passed on as if it were ours
            if f not in found and row[f] not in (None, "") and f not in external:
                found[f] = row[f]
    return found


def fill_missing(conn: sqlite3.Connection | None, fields: dict, use_openfoodfacts: bool = True) -> dict:
    """Copy of an extracted product with gaps filled; sources noted in external_fields."""
    barcode = normalise_barcode(fields.get("barcode"))
    wanted = _missing(fields)
    if barcode is None or not wanted:
        return fields

    out = {**fields, "barcode": barcode}
    sources = dict(out.get("external_fields") or {})

    if conn is not None:
        for f, value in from_our_data(conn, barcode, wanted).items():
            out[f] = value
            sources[f] = OUR_DATA

    still = _missing(out)
    if still and use_openfoodfacts:
        found = openfoodfacts.lookup(barcode) or {}
        for f in still:
            if found.get(f) not in (None, ""):
                out[f] = found[f]
                sources[f] = openfoodfacts.SOURCE

    out["external_fields"] = sources
    return out


def fill_existing(conn: sqlite3.Connection) -> tuple[int, int]:
    """
    Admin button: fill gaps on items already in the DB that have a barcode.
    Returns (items checked, fields filled).
    """
    rows = conn.execute(
        "SELECT * FROM items WHERE barcode IS NOT NULL AND status != 'rejected' "
        "AND (kcal IS NULL OR protein_g IS NULL OR ingredients_text IS NULL OR ingredients_text = '')"
    ).fetchall()
    filled_total = 0
    for row in rows:
        before = dict(row)
        before["external_fields"] = json.loads(before.get("external_fields") or "{}")
        after = fill_missing(conn, before)
        changed = [f for f in FILLABLE if before.get(f) in (None, "") and after.get(f) not in (None, "")]
        if not changed:
            continue
        sets = ", ".join(f"{f} = ?" for f in changed)
        conn.execute(
            f"UPDATE items SET {sets}, external_fields = ? WHERE item_id = ?",
            [after[f] for f in changed] + [json.dumps(after["external_fields"]), row["item_id"]],
        )
        filled_total += len(changed)
    conn.commit()
    return len(rows), filled_total
