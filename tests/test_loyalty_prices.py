"""Card prices (Clubcard etc.) must show everywhere a price or saving is shown."""

from datetime import date

from streamlit.testing.v1 import AppTest

import approval
import db
from extract import build_deal, build_item
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _approve_tesco_basket(conn):
    for cat, name, price, card in (("main", "Chicken wrap", 2.75, 2.50),
                                   ("snack", "Sea Salt crisps", 1.10, 1.00),
                                   ("drink", "Coke Zero", 1.70, 1.50)):
        item = build_item({"name": name, "category": cat, "price_gbp": price, "loyalty_price_gbp": card,
                           "meal_deal_eligible": True, "confidence": "high", "allergens": []},
                          "tesco-tcr", f"tesco-tcr/{cat}/x.jpg", date.today(), "u-sam")
        data = item.model_dump(); data["last_seen"] = item.last_seen.isoformat()
        approval.approve(conn, approval.queue_item(conn, data), "item")
    deal = build_deal({"name": "Meal Deal", "price_gbp": 4.25, "loyalty_price_gbp": 3.85,
                       "loyalty_scheme": "Clubcard"}, "tesco-tcr", "tesco-tcr/general/d.jpg", date.today(), "u-sam")
    approval.approve(conn, approval.queue_deal(conn, {**deal.model_dump(), "last_seen": date.today().isoformat()}), "deal")


def _shop_page(tmp_path, monkeypatch, clubcard: bool) -> str:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    _approve_tesco_basket(db.get_connection())
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.session_state["screen"] = "detail"
    at.session_state["detail_shop_id"] = "tesco-tcr"
    at.session_state["card_clubcard"] = clubcard
    at.run()
    assert not at.exception
    return " ".join(m.value for m in at.markdown)


def test_shop_page_shows_the_clubcard_deal_price(tmp_path, monkeypatch):
    page = _shop_page(tmp_path, monkeypatch, clubcard=True)
    assert "£3.85" in page and "Clubcard price" in page
    assert "£4.25 without" in page                       # the shelf price stays visible
    assert "card price" in page                          # item prices use the card too


def test_shop_page_without_a_card_shows_the_shelf_price(tmp_path, monkeypatch):
    page = _shop_page(tmp_path, monkeypatch, clubcard=False)
    assert "£4.25" in page and "Clubcard price" not in page
