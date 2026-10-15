"""Tests for db.py migrations."""

import sqlite3

import pytest

import db


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(db, "_auto_seed_items", lambda conn: None)
    return tmp_path / "t.db"


def test_old_sainsburys_rows_move_to_warren_street(fresh):
    # An older DB: shop + item + task under the old id
    old = sqlite3.connect(fresh)
    old.executescript(db._SCHEMA)
    old.execute("INSERT INTO shops VALUES ('sainsburys-tcr','sainsburys','Sainsbury''s Local','TCR',6,'2026-10-12',51.52,-0.135)")
    old.execute("""INSERT INTO items (item_id, shop_id, name, category, price_gbp, temperature, source_image,
                   source_text, last_seen, submitted_via, status)
                   VALUES ('s1','sainsburys-tcr','Wrap','main',3,'cold','sainsburys-tcr/main/x.jpg','t','2026-10-15','upload','approved')""")
    old.execute("INSERT INTO tasks (task_id, shop_id, item_name, needed, ask) VALUES ('t1','sainsburys-tcr','Wrap','price','ask')")
    old.commit(); old.close()

    conn = db.get_connection()
    assert conn.execute("SELECT 1 FROM shops WHERE shop_id='sainsburys-tcr'").fetchone() is None
    shop = conn.execute("SELECT * FROM shops WHERE shop_id='sainsburys-warren-st'").fetchone()
    assert shop["address"] == "21 Hampstead Road, London NW1"
    item = conn.execute("SELECT shop_id, source_image FROM items WHERE item_id='s1'").fetchone()
    assert tuple(item) == ("sainsburys-warren-st", "sainsburys-warren-st/main/x.jpg")
    assert conn.execute("SELECT shop_id FROM tasks WHERE task_id='t1'").fetchone()[0] == "sainsburys-warren-st"
    conn.close()


def test_seed_shop_edits_reach_existing_db(fresh):
    conn = db.get_connection()
    conn.execute("UPDATE shops SET name='Old name' WHERE shop_id='tesco-tcr'"); conn.commit(); conn.close()
    db._conn = None
    conn = db.get_connection()
    assert conn.execute("SELECT name FROM shops WHERE shop_id='tesco-tcr'").fetchone()[0] == "Tesco Express"
    conn.close()
