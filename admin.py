"""
Team-only admin mode for the review queue.

One shared passcode, read from ADMIN_PASSCODE in Streamlit secrets (deployed) or
the environment / .env (local). Never in code or the repo.

- No passcode configured → admin mode can't be unlocked (fails closed).
- Unlock lasts for this browser session; "Lock" ends it.
- Passcode compared with hmac.compare_digest (constant time).
- After MAX_ATTEMPTS wrong tries, the session is locked out for LOCKOUT_SECONDS.

Students still identify by handle only — this gate is for the team, not users.
"""

from __future__ import annotations

import hmac
import os
import time

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

_UNLOCKED = "admin_unlocked"
_FAILS = "admin_failed_attempts"
_LOCKED_UNTIL = "admin_locked_until"


def configured_passcode() -> str | None:
    try:
        value = st.secrets.get("ADMIN_PASSCODE")
    except Exception:  # no secrets.toml
        value = None
    value = value or os.environ.get("ADMIN_PASSCODE")
    return value or None


def check_passcode(attempt: str, passcode: str | None) -> bool:
    if not passcode or not attempt:
        return False
    return hmac.compare_digest(attempt.encode(), passcode.encode())


def is_admin() -> bool:
    return bool(st.session_state.get(_UNLOCKED)) and configured_passcode() is not None


def lock() -> None:
    st.session_state[_UNLOCKED] = False


def _try_unlock() -> None:
    """on_click callback for the Unlock button."""
    now = time.time()
    if st.session_state.get(_LOCKED_UNTIL, 0) > now:
        return
    if check_passcode(st.session_state.get("admin_passcode_input", ""), configured_passcode()):
        st.session_state[_UNLOCKED] = True
        st.session_state[_FAILS] = 0
    else:
        fails = st.session_state.get(_FAILS, 0) + 1
        st.session_state[_FAILS] = fails
        if fails >= MAX_ATTEMPTS:
            st.session_state[_LOCKED_UNTIL] = now + LOCKOUT_SECONDS
            st.session_state[_FAILS] = 0
    st.session_state["admin_passcode_input"] = ""


def render_admin_sidebar() -> None:
    """Small 'Team' expander at the bottom of the sidebar."""
    with st.sidebar.expander("Team", expanded=False):
        if configured_passcode() is None:
            st.caption("Admin mode is off — no ADMIN_PASSCODE is set.")
            return
        if is_admin():
            st.caption("✅ Admin mode on — Review queue unlocked.")
            st.button("Lock", key="admin_lock", on_click=lock, use_container_width=True)
            return
        locked_for = st.session_state.get(_LOCKED_UNTIL, 0) - time.time()
        if locked_for > 0:
            st.caption(f"Too many wrong tries. Try again in {int(locked_for) + 1}s.")
            return
        st.text_input("Team passcode", type="password", key="admin_passcode_input")
        st.button("Unlock", key="admin_unlock", on_click=_try_unlock, use_container_width=True)
        if st.session_state.get(_FAILS):
            st.caption("Wrong passcode.")
