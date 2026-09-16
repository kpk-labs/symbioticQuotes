import time

import streamlit as st

from .config import FETCH_TTL_SECONDS


def get_cached(key: str, fetch_fn, force: bool = False) -> dict:
    """TTL cache in session_state that keeps the last good value on failure.

    Plain st.cache_data doesn't retain a prior result once a call raises, and
    this app's whole point is to never blank the page on one bad request.
    Returns {"ts", "value", "error"} - "error" set means this call failed and
    "value" is a stale fallback (or None if we never had one).
    """
    now = time.time()
    cached = st.session_state.get(key)

    if not force and cached and (now - cached["ts"] < FETCH_TTL_SECONDS) and cached["error"] is None:
        return cached

    try:
        value = fetch_fn()
        st.session_state[key] = {"ts": now, "value": value, "error": None}
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
        if cached and cached["value"] is not None:
            st.session_state[key] = {"ts": cached["ts"], "value": cached["value"], "error": str(exc)}
        else:
            st.session_state[key] = {"ts": now, "value": None, "error": str(exc)}

    return st.session_state[key]


def format_age(ts: float) -> str:
    seconds = int(time.time() - ts)
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    return f"{minutes}m {seconds % 60}s ago"
