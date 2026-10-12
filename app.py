"""
Meal Deal Finder — Streamlit UI.

Screens:
  1. Find       — three-section results (Section A/B/C) + Map view tab
  2. Shop detail — interactive basket swap + full catalogue table
  3. Add photo  — upload, extract, submit for review
  4. My credits — balance, history, mocked rewards
  5. Review queue — approve/reject (team only)
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from streamlit_folium import st_folium

import approval
import ledger
from db import (
    fetch_approved_deals,
    fetch_approved_items,
    fetch_all_shops,
    get_connection,
    get_user_credit_balance,
    upsert_user,
)
from extract import extract_item, extract_deal, strip_exif
from map_view import build_map
from models import Preferences
from optimiser import (
    get_results,
    hard_filter,
    _row_to_item,
    _row_to_shop,
    _row_to_deal,
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Meal Deal Finder",
    page_icon="🥪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DB + cached data loaders
# ---------------------------------------------------------------------------

@st.cache_resource
def _conn():
    return get_connection()


@st.cache_data(ttl=30)
def _load_data():
    conn = _conn()
    shops  = [_row_to_shop(r)  for r in fetch_all_shops(conn)]
    items  = [_row_to_item(r)  for r in fetch_approved_items(conn)]
    # also include pending items (shown with Unverified tag when no allergen filter)
    pending_rows = conn.execute(
        "SELECT * FROM items WHERE status = 'pending'"
    ).fetchall()
    pending = [_row_to_item(r) for r in pending_rows]
    deals  = [_row_to_deal(r)  for r in fetch_approved_deals(conn)]
    return shops, items + pending, deals


# ---------------------------------------------------------------------------
# User identity
# ---------------------------------------------------------------------------

def _ensure_user():
    conn = _conn()
    handle = st.session_state.get("username", "").strip()
    if not handle:
        return None
    user_id = f"u-{handle.lower().replace(' ', '-')}"
    upsert_user(conn, user_id, handle)
    return user_id


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

ALLERGENS = ["Gluten", "Milk", "Egg", "Nuts", "Sesame", "Soy", "Fish", "Shellfish"]
DIETS     = ["Vegetarian", "Vegan", "Halal"]


def render_sidebar() -> Preferences:
    st.sidebar.title("🥪 Meal Deal Finder")

    # Username
    st.sidebar.text_input(
        "Your name (for credits)",
        key="username",
        placeholder="e.g. Alex",
    )
    st.sidebar.divider()

    # Allergens — safety first, red label
    st.sidebar.markdown(
        '<p style="color:#DC2626;font-weight:700;margin-bottom:4px">Allergies — avoid</p>',
        unsafe_allow_html=True,
    )
    avoid = [a for a in ALLERGENS if st.sidebar.checkbox(a, key=f"avoid_{a}")]
    if avoid:
        st.sidebar.caption("Items with unchecked allergen labels are hidden.")
    st.sidebar.divider()

    # Diet
    st.sidebar.markdown("**Diet**")
    diet_flags = [d for d in DIETS if st.sidebar.checkbox(d, key=f"diet_{d}")]
    st.sidebar.divider()

    # Preferences
    st.sidebar.markdown("**Preferences**")
    max_price = st.sidebar.slider("Max price (£)", 2.0, 14.0, 6.0, step=0.25)
    walk_limit = st.sidebar.slider("Walking limit", 2, 30, 10, format="%d min")
    temp = st.sidebar.radio(
        "Hot or cold main",
        options=["any", "hot", "cold"],
        horizontal=True,
        key="temp_pref",
    )
    st.sidebar.divider()

    # Loyalty
    st.sidebar.markdown("**Loyalty cards**")
    loyalty = st.sidebar.toggle("I have loyalty cards (Clubcard / Nectar)", value=False)
    st.sidebar.divider()

    # Sort
    sort_label = st.sidebar.selectbox(
        "Sort by",
        options=["Quality", "Distance", "Price (low to high)"],
        key="sort_select",
    )
    sort_map = {"Quality": "quality", "Distance": "distance", "Price (low to high)": "price"}

    return Preferences(
        sort=sort_map[sort_label],
        temperature_pref=temp,
        max_price_gbp=max_price,
        max_walking_minutes=float(walk_limit),
        diet_flags=[d.lower() for d in diet_flags],
        allergens_exclude=[a.lower() for a in avoid],
        has_clubcard=loyalty,
        has_nectar=loyalty,
    )


# ---------------------------------------------------------------------------
# Result card components
# ---------------------------------------------------------------------------

def _freshness_badge(last_seen_str: str) -> str:
    try:
        days = (date.today() - date.fromisoformat(last_seen_str)).days
    except Exception:
        return ""
    if days > 14:
        return f'<span style="background:#F1F5F9;color:#94A3B8;font-size:11px;padding:2px 8px;border-radius:999px">● Seen {days}d ago</span>'
    if days > 7:
        return f'<span style="background:#FFFBEB;color:#D97706;font-size:11px;padding:2px 8px;border-radius:999px">● Seen {days}d ago</span>'
    return f'<span style="background:#F0FDF4;color:#16A34A;font-size:11px;padding:2px 8px;border-radius:999px">● Seen {days}d ago</span>'


def _allergen_line(items_list, avoid: list[str]) -> str:
    unknown = any(not i.allergens and i.allergens is not None for i in items_list)
    # null allergens (empty list + unknown) handled at filter level
    has_null = any(i.allergens is None for i in items_list)
    if has_null:
        return "⚠️ **Allergens not checked** — label had no allergen text"
    all_allergens = sorted({a for i in items_list for a in i.allergens})
    allergen_str = ", ".join(all_allergens) if all_allergens else "none listed"
    return f"Contains (from label): {allergen_str}"


def render_result_card(lunch, rank: int, prefs: Preferences, featured: bool = False):
    from models import Lunch
    border = "2px solid #0F7B5F" if featured else "1px solid #E3E3DE"
    bg = "#F0FDF4" if featured else "#FFFFFF"

    with st.container(border=False):
        st.markdown(
            f'<div style="border:{border};border-radius:8px;background:{bg};padding:16px;margin-bottom:12px">',
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            rank_str = f"#{rank} " if rank > 0 else ""
            badge = ' <span style="background:#0F7B5F;color:white;font-size:10px;padding:2px 8px;border-radius:999px">Best match</span>' if featured else ""
            st.markdown(f"**{rank_str}{lunch.shop.name}**{badge}", unsafe_allow_html=True)
            st.caption(f"{lunch.shop.walking_minutes:.0f} min walk")
            st.markdown(
                f"{lunch.main.name} + {lunch.snack.name} + {lunch.drink.name}"
            )
            st.markdown(
                _allergen_line([lunch.main, lunch.snack, lunch.drink], prefs.allergens_exclude),
                unsafe_allow_html=True,
            )
            if lunch.why:
                st.caption(f"*{lunch.why}*")

        with col2:
            sep_price = lunch.main.price_gbp + lunch.snack.price_gbp + lunch.drink.price_gbp
            st.markdown(f"### £{lunch.price_gbp:.2f}")
            if lunch.used_deal and sep_price > lunch.price_gbp:
                st.markdown(
                    f'<span style="text-decoration:line-through;color:#94A3B8">£{sep_price:.2f} separately</span>',
                    unsafe_allow_html=True,
                )
                st.caption(f"✅ Meal deal saves £{sep_price - lunch.price_gbp:.2f}")
            else:
                st.caption("Bought separately — no deal")
            # Freshness
            oldest = max(
                (date.today() - date.fromisoformat(i.last_seen)).days
                for i in [lunch.main, lunch.snack, lunch.drink]
                if isinstance(i.last_seen, str)
            )
            st.markdown(_freshness_badge(
                (date.today() - __import__("datetime").timedelta(days=oldest)).isoformat()
            ), unsafe_allow_html=True)

        with col3:
            if st.button("See basket →", key=f"open_{lunch.shop.shop_id}_{rank}"):
                st.session_state["detail_shop_id"] = lunch.shop.shop_id
                st.session_state["screen"] = "detail"
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Screen 1: Find
# ---------------------------------------------------------------------------

def screen_find(prefs: Preferences):
    shops, items, deals = _load_data()
    primary, alternatives, other_shops = get_results(shops, items, deals, prefs)

    list_tab, map_tab = st.tabs(["List view", "Map view"])

    with list_tab:
        if primary is None:
            # Diagnose which filter is blocking
            filtered = hard_filter(items, prefs)
            in_range = [s for s in shops if s.walking_minutes <= prefs.max_walking_minutes]
            if not in_range:
                st.info("← No shops within your walking limit. Try increasing it.")
            elif not filtered:
                st.info("← No items match your filters. Try relaxing your diet or allergen settings.")
            else:
                st.info("← Set your preferences on the left to find the best lunch near you.")
            return

        # Section A — featured best option
        st.markdown("#### Your best option")
        render_result_card(primary, rank=1, prefs=prefs, featured=True)

        # Section B — alternatives at same shop
        if alternatives:
            st.markdown(f"#### More at {primary.shop.name}")
            for i, alt in enumerate(alternatives, start=2):
                render_result_card(alt, rank=i, prefs=prefs, featured=False)

        # Section C — other shops
        if other_shops:
            st.divider()
            st.markdown("#### Other nearby shops")
            for i, lunch in enumerate(other_shops, start=len(alternatives) + 2):
                render_result_card(lunch, rank=i, prefs=prefs, featured=False)

        # Stale shops — greyed
        all_ranked_ids = (
            {primary.shop.shop_id}
            | {l.shop.shop_id for l in alternatives}
            | {l.shop.shop_id for l in other_shops}
        )
        stale_items = [i for i in items
                       if isinstance(i.last_seen, str)
                       and (date.today() - date.fromisoformat(i.last_seen)).days > 14]
        stale_shop_ids = {i.shop_id for i in stale_items} - all_ranked_ids
        if stale_shop_ids:
            st.caption("Not ranked — last seen over 14 days ago")
            for shop in shops:
                if shop.shop_id in stale_shop_ids:
                    st.markdown(
                        f'<div style="opacity:0.4;border:1px solid #E3E3DE;border-radius:8px;'
                        f'padding:12px;margin-bottom:8px">'
                        f'<b>{shop.name}</b> · {shop.walking_minutes:.0f} min walk · '
                        f'<span style="color:#94A3B8">Data too old</span></div>',
                        unsafe_allow_html=True,
                    )

        st.caption("Sponsors never affect ranking.")

    with map_tab:
        all_ranked = [primary] + alternatives + other_shops if primary else []
        fmap = build_map(
            ranked_lunches=all_ranked,
            all_shops=shops,
            walking_limit_minutes=prefs.max_walking_minutes,
        )
        st_folium(fmap, width=900, height=500, returned_objects=[])


# ---------------------------------------------------------------------------
# Screen 2: Shop detail
# ---------------------------------------------------------------------------

def screen_detail():
    shops, all_items, deals = _load_data()
    shop_id = st.session_state.get("detail_shop_id")
    shop = next((s for s in shops if s.shop_id == shop_id), None)

    if shop is None:
        st.error("Shop not found.")
        if st.button("← Back"):
            st.session_state["screen"] = "find"
            st.rerun()
        return

    if st.button("← Back to results"):
        st.session_state["screen"] = "find"
        st.rerun()

    st.markdown(f"## {shop.name}")
    st.caption(f"{shop.walking_minutes:.0f} min walk from campus")

    # Items for this shop
    shop_items = [i for i in all_items if i.shop_id == shop_id and i.status in ("approved", "pending")]
    mains  = [i for i in shop_items if i.category == "main"]
    snacks = [i for i in shop_items if i.category == "snack"]
    drinks = [i for i in shop_items if i.category == "drink"]
    shop_deals = [d for d in deals if d.shop_id == shop_id]

    if not mains or not snacks or not drinks:
        st.info("Not enough items to build a full basket for this shop yet.")
        return

    # Per-category dropdowns
    def _item_label(item) -> str:
        hot = " · hot" if item.temperature == "hot" else ""
        nd = " · not in deal" if item.meal_deal_eligible is False else ""
        pend = " · unverified" if item.status == "pending" else ""
        return f"{item.name} — £{item.price_gbp:.2f}{hot}{nd}{pend}"

    col1, col2, col3 = st.columns(3)
    key_prefix = f"detail_{shop_id}"

    with col1:
        st.caption("MAIN")
        main_idx = st.selectbox(
            "Main", range(len(mains)),
            format_func=lambda i: _item_label(mains[i]),
            key=f"{key_prefix}_main",
        )
        main = mains[main_idx]
        st.markdown(f"**{main.name}**")
        if main.temperature == "hot":
            st.caption("🔥 hot")
        st.caption(f"£{main.price_gbp:.2f}")
        allergens_str = ", ".join(main.allergens) if main.allergens else ("not checked" if main.allergens is None else "none listed")
        st.caption(f"Allergens: {allergens_str}")
        st.markdown(_freshness_badge(str(main.last_seen)), unsafe_allow_html=True)
        if main.status == "pending":
            st.caption("⚠️ Unverified")

    with col2:
        st.caption("SNACK")
        snack_idx = st.selectbox(
            "Snack", range(len(snacks)),
            format_func=lambda i: _item_label(snacks[i]),
            key=f"{key_prefix}_snack",
        )
        snack = snacks[snack_idx]
        st.markdown(f"**{snack.name}**")
        st.caption(f"£{snack.price_gbp:.2f}")
        allergens_str = ", ".join(snack.allergens) if snack.allergens else "none listed"
        st.caption(f"Allergens: {allergens_str}")
        st.markdown(_freshness_badge(str(snack.last_seen)), unsafe_allow_html=True)

    with col3:
        st.caption("DRINK")
        drink_idx = st.selectbox(
            "Drink", range(len(drinks)),
            format_func=lambda i: _item_label(drinks[i]),
            key=f"{key_prefix}_drink",
        )
        drink = drinks[drink_idx]
        st.markdown(f"**{drink.name}**")
        st.caption(f"£{drink.price_gbp:.2f}")
        allergens_str = ", ".join(drink.allergens) if drink.allergens else "none listed"
        st.caption(f"Allergens: {allergens_str}")
        st.markdown(_freshness_badge(str(drink.last_seen)), unsafe_allow_html=True)

    # Reset button
    default_idxs = (0, 0, 0)
    current_idxs = (main_idx, snack_idx, drink_idx)
    if current_idxs != default_idxs:
        if st.button("Reset to best basket"):
            for k in [f"{key_prefix}_main", f"{key_prefix}_snack", f"{key_prefix}_drink"]:
                st.session_state[k] = 0
            st.rerun()

    st.divider()

    # Pricing comparison
    sep_price = main.price_gbp + snack.price_gbp + drink.price_gbp
    deal_eligible = (
        main.meal_deal_eligible is not False
        and snack.meal_deal_eligible is not False
        and drink.meal_deal_eligible is not False
    )
    deal = shop_deals[0] if shop_deals else None
    deal_price = deal.price_gbp if deal else None
    is_deal_better = deal_price is not None and deal_eligible and deal_price < sep_price

    pc1, pc2 = st.columns(2)
    with pc1:
        border = "2px solid #0F7B5F" if is_deal_better else "1px solid #E3E3DE"
        st.markdown(
            f'<div style="border:{border};border-radius:8px;padding:16px">',
            unsafe_allow_html=True,
        )
        st.caption("Meal deal price")
        if deal is None:
            st.markdown("**No deal at this shop**")
        elif not deal_eligible:
            st.markdown(f"**£{deal.price_gbp:.2f}** — not available")
            st.caption("An item you picked isn't in the meal deal.")
        else:
            st.markdown(f"**£{deal.price_gbp:.2f}**")
            if is_deal_better:
                st.caption(f"✅ Best option — saves £{sep_price - deal.price_gbp:.2f}")
        st.markdown("</div>", unsafe_allow_html=True)

    with pc2:
        border = "2px solid #0F7B5F" if not is_deal_better else "1px solid #E3E3DE"
        st.markdown(
            f'<div style="border:{border};border-radius:8px;padding:16px">',
            unsafe_allow_html=True,
        )
        st.caption("Bought separately")
        st.markdown(f"**£{sep_price:.2f}**")
        if not is_deal_better:
            st.caption("✅ Best option")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # Full catalogue table
    st.markdown(f"#### Everything we've seen here")
    st.caption(f"{len(shop_items)} items catalogued from photos")

    search = st.text_input("Search items", placeholder="e.g. wrap, vegan", key=f"{key_prefix}_search")
    cat_filter = st.radio("Category", ["All", "Mains", "Snacks", "Drinks"], horizontal=True, key=f"{key_prefix}_cat")

    cat_map = {"All": None, "Mains": "main", "Snacks": "snack", "Drinks": "drink"}
    filtered = [
        i for i in shop_items
        if (not cat_map[cat_filter] or i.category == cat_map[cat_filter])
        and (not search or search.lower() in i.name.lower())
    ]

    for item in filtered:
        days_old = (date.today() - date.fromisoformat(str(item.last_seen))).days
        opacity = "0.4" if days_old > 14 else "1.0"
        hot_tag = " · 🔥 hot" if item.temperature == "hot" else ""
        nd_tag = " · *not in deal*" if item.meal_deal_eligible is False else ""
        pend_tag = " · ⚠️ unverified" if item.status == "pending" else ""
        allergens = ", ".join(item.allergens) if item.allergens else ("not checked" if item.allergens is None else "none")

        row_cols = st.columns([3, 1, 1, 2, 1, 1])
        with row_cols[0]:
            st.markdown(
                f'<div style="opacity:{opacity}"><b>{item.name}</b>{hot_tag}{nd_tag}{pend_tag}</div>',
                unsafe_allow_html=True,
            )
        with row_cols[1]:
            st.caption(item.category.upper())
        with row_cols[2]:
            st.markdown(f"£{item.price_gbp:.2f}")
        with row_cols[3]:
            st.caption(allergens)
        with row_cols[4]:
            st.markdown(_freshness_badge(str(item.last_seen)), unsafe_allow_html=True)
        with row_cols[5]:
            cat = item.category
            options = {"main": mains, "snack": snacks, "drink": drinks}[cat]
            try:
                idx = options.index(item)
            except ValueError:
                idx = None
            current_key = f"{key_prefix}_{cat}"
            if idx is not None and st.session_state.get(current_key, 0) == idx:
                st.caption("In basket")
            elif idx is not None:
                if st.button("Swap in", key=f"swap_{item.item_id}"):
                    st.session_state[current_key] = idx
                    st.rerun()


# ---------------------------------------------------------------------------
# Screen 3: Add a photo
# ---------------------------------------------------------------------------

def screen_upload():
    st.markdown("## Add a photo")
    st.caption("Snap a shelf label. Earn credits once our team approves it.")

    user_id = _ensure_user()
    if not user_id:
        st.warning("Enter your name in the sidebar to earn credits.")

    col_upload, col_result = st.columns(2)

    with col_upload:
        uploaded = st.file_uploader(
            "Drag a photo here or browse",
            type=["jpg", "jpeg", "png", "webp"],
            key="photo_upload",
        )
        shop_options = {s.name: s.shop_id for s in _load_data()[0]}
        shop_name = st.selectbox("Which shop is this from?", list(shop_options.keys()))
        shop_id = shop_options[shop_name]

    with col_result:
        if uploaded is None:
            st.info("Upload a photo to see what we read from it.")
            return

        # Save file
        save_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{uploaded.name}"
        save_path.write_bytes(uploaded.read())

        with st.spinner("Reading your photo… you can keep browsing."):
            try:
                item = extract_item(
                    save_path,
                    shop_id=shop_id,
                    submitted_via="upload",
                    submitted_by=user_id,
                    strip_location=True,
                )
                st.success("Photo read successfully.")
            except Exception as exc:
                st.error(
                    f"We couldn't read a price label in that photo. "
                    f"Hold the phone steady, fill the frame with the label, and try again.\n\n_{exc}_"
                )
                return

        # Show extracted data
        st.markdown("**What we read**")
        rows = [
            ("Shop", shop_name),
            ("Item", item.name),
            ("Category", item.category),
            ("Price", f"£{item.price_gbp:.2f}"),
            ("Meal deal eligible", str(item.meal_deal_eligible)),
            ("Allergens", ", ".join(item.allergens) if item.allergens else "none on label"),
            ("Diet flags", ", ".join(item.diet_flags) if item.diet_flags else "none on label"),
            ("Confidence", item.confidence),
        ]
        for label, val in rows:
            st.markdown(f"**{label}:** {val}")

        if item.needs_review:
            st.warning("Label was partially readable — marked for team review before credits are paid.")

        st.caption("⚠️ We only report allergen info printed on the label. Always check the packaging.")

        if st.button("Looks right — submit for review", type="primary"):
            conn = _conn()
            item_id = approval.queue_item(conn, item.model_dump())
            st.session_state["last_submitted_id"] = item_id
            st.success(
                "Sent — awaiting review. 0 credits for now. "
                "You'll earn up to 20 credits once it's approved."
            )


# ---------------------------------------------------------------------------
# Screen 4: My credits
# ---------------------------------------------------------------------------

def screen_credits():
    st.markdown("## My credits")
    user_id = _ensure_user()
    if not user_id:
        st.info("Enter your name in the sidebar to see your credits.")
        return

    conn = _conn()
    handle = st.session_state.get("username", "")
    balance = get_user_credit_balance(conn, user_id)
    pending_est = ledger.get_pending_credits(conn, user_id)

    st.markdown(f"Hello, **{handle}**")

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Ready to spend", f"{balance} credits")
    with c2:
        st.metric("Awaiting review (estimate)", f"{pending_est} credits")
        st.caption("0 credits until approved")

    st.divider()

    # Rewards
    st.markdown("#### Rewards from sponsors")
    rewards = conn.execute("SELECT * FROM rewards").fetchall()
    if rewards:
        for r in rewards:
            rc1, rc2 = st.columns([3, 1])
            with rc1:
                st.markdown(f"**{r['title']}**")
                st.caption(r["sponsor"])
            with rc2:
                can_afford = balance >= r["cost_credits"]
                if st.button(
                    f"{r['cost_credits']} credits",
                    key=f"redeem_{r['reward_id']}",
                    type="primary" if can_afford else "secondary",
                    disabled=not can_afford or r["codes_remaining"] == 0,
                ):
                    code = ledger.redeem_reward(conn, user_id, r["reward_id"])
                    if code:
                        st.success(f"Redeemed! Your code: **{code}**")
                        _load_data.clear()
                        st.rerun()
                    else:
                        st.error("Redemption failed — no codes remaining or insufficient balance.")
    st.caption("ℹ️ Sponsors shown here are placeholders for the demo. Real partnerships come after launch.")

    st.divider()

    # History
    st.markdown("#### History")
    history = ledger.get_credit_history(conn, user_id)
    if not history:
        st.caption("No credit events yet.")
    else:
        for event in history:
            sign = "+" if event["credits"] > 0 else ""
            reason_label = event["reason"].replace("_", " ")
            ts = event["created_at"][:10]
            st.markdown(f"`{sign}{event['credits']}` · {reason_label} · {ts}")


# ---------------------------------------------------------------------------
# Screen 5: Review queue (team only)
# ---------------------------------------------------------------------------

def screen_review():
    st.markdown("## Review queue")
    st.caption("Team only — approve or reject submitted photos.")

    conn = _conn()
    pending_items = approval.get_pending_items(conn)
    pending_deals = approval.get_pending_deals(conn)
    total = len(pending_items) + len(pending_deals)

    if total == 0:
        st.success("Queue is empty — nothing to review.")
        return

    st.caption(f"{total} item{'s' if total != 1 else ''} pending")

    for row in list(pending_items) + list(pending_deals):
        record_type = "deal" if "deal_id" in row.keys() else "item"
        record_id = row["deal_id"] if record_type == "deal" else row["item_id"]

        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                src = UPLOAD_DIR / row["source_image"]
                if src.exists():
                    st.image(str(src), width=200)
                else:
                    st.caption("[label photo]")

            with c2:
                shop_name = row.get("shop_id", "Unknown shop")
                st.markdown(f"**{shop_name}** · {row.get('name', '')}")
                if record_type == "item":
                    allergens = json.loads(row.get("allergens", "[]"))
                    st.caption(
                        f"{row.get('category','').upper()} · "
                        f"£{row.get('price_gbp', 0):.2f} · "
                        f"Allergens: {', '.join(allergens) if allergens else 'not on label'}"
                    )
                    st.caption(f"Confidence: {row.get('confidence', '?')} · Submitted by: {row.get('submitted_by', 'anonymous')}")
                else:
                    st.caption(f"Deal · £{row.get('price_gbp', 0):.2f}")

                st.caption(str(row.get("last_seen", "")))

                done_key = f"done_{record_id}"
                if st.session_state.get(done_key):
                    st.markdown(f"**{st.session_state[done_key]}**")
                else:
                    ap_col, rj_col = st.columns(2)
                    with ap_col:
                        if st.button("Approve", key=f"approve_{record_id}", type="primary"):
                            credits = approval.approve(conn, record_id, record_type)
                            msg = f"Approved — {credits} credits paid" if credits else "Approved"
                            st.session_state[done_key] = msg
                            _load_data.clear()
                            st.rerun()
                    with rj_col:
                        if st.button("Reject", key=f"reject_{record_id}"):
                            approval.reject(conn, record_id, record_type)
                            st.session_state[done_key] = "Rejected"
                            _load_data.clear()
                            st.rerun()


# ---------------------------------------------------------------------------
# Navigation + main
# ---------------------------------------------------------------------------

SCREENS = {
    "Find": "find",
    "Add a photo": "upload",
    "My credits": "credits",
    "Review queue": "review",
}


def main():
    prefs = render_sidebar()

    if "screen" not in st.session_state:
        st.session_state["screen"] = "find"

    # Top nav
    nav_cols = st.columns(len(SCREENS))
    for col, (label, key) in zip(nav_cols, SCREENS.items()):
        with col:
            if st.button(label, use_container_width=True):
                st.session_state["screen"] = key
                st.rerun()

    st.divider()

    screen = st.session_state["screen"]

    if screen == "find":
        screen_find(prefs)
    elif screen == "detail":
        screen_detail()
    elif screen == "upload":
        screen_upload()
    elif screen == "credits":
        screen_credits()
    elif screen == "review":
        screen_review()


if __name__ == "__main__":
    main()
