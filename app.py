import os

import streamlit as st
from dotenv import load_dotenv

from src import chain, model, rfq, safe
from src.config import ADAPTER, LOGOS, SAFE
from src.util import format_age, get_cached

load_dotenv()

KPKUSERNAME = os.getenv("KPKUSERNAME")
KPKPASSWORD = os.getenv("KPKPASSWORD")

st.set_page_config(page_title="KPK Symbiotic LL quotes", layout="wide", page_icon="\U0001F4B1")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("KPK Symbiotic LL quotes")
    with st.form("login_form"):
        input_username = st.text_input("Username")
        input_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if input_username == KPKUSERNAME and input_password == KPKPASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()


# --- Data sources (60s TTL, last-good-value-on-failure - see src/util.py) ---

def fetch_chain_bundle(token_nonce_pairs):
    w3 = chain.get_web3()
    adapter = chain.get_adapter(w3)
    block_number = w3.eth.block_number
    tokens = chain.fetch_roster(w3, adapter)
    token_states = [chain.fetch_token_state(w3, adapter, t) for t in tokens]
    revocations = chain.fetch_revocations(w3, adapter, token_nonce_pairs)
    return {"block_number": block_number, "tokens": token_states, "revocations": revocations}


def fetch_rfq_bundle(tokens):
    liquidity = {}
    for t in tokens:
        data = rfq.fetch_liquidity(t["address"])
        if data and data.get("totalLiquidity") is not None:
            liquidity[t["address"].lower()] = int(data["totalLiquidity"]) / 1e6
    return {"liquidity": liquidity, "orders": rfq.fetch_filled_orders()}


force_refresh = st.session_state.pop("force_refresh", False)

quotes_state = get_cached("quotes", safe.fetch_discount_messages, force=force_refresh)
quotes_raw = quotes_state["value"] or []

token_nonce_pairs = {
    (m["message"]["message"]["tokenToRedeem"].lower(), str(m["message"]["message"]["nonce"]).replace(" ", ""))
    for m in quotes_raw
}

chain_state = get_cached("chain", lambda: fetch_chain_bundle(token_nonce_pairs), force=force_refresh)
chain_value = chain_state["value"] or {"block_number": None, "tokens": [], "revocations": {}}

rfq_state = get_cached("rfq", lambda: fetch_rfq_bundle(chain_value["tokens"]), force=force_refresh)
rfq_value = rfq_state["value"] or {"liquidity": {}, "orders": []}

rows = model.build_rows(chain_value["tokens"], quotes_raw, chain_value["revocations"], rfq_value["liquidity"])


# --- Header ---

st.title("KPK Symbiotic LL quotes")
st.caption(
    f"Safe [`{SAFE}`](https://etherscan.io/address/{SAFE}) · "
    f"Adapter [`{ADAPTER}`](https://etherscan.io/address/{ADAPTER})"
)

header_cols = st.columns([2, 2, 2, 1])
header_cols[0].markdown(f"quotes: {format_age(quotes_state['ts'])}" + (" ⚠️" if quotes_state["error"] else ""))
header_cols[1].markdown(f"chain: {format_age(chain_state['ts'])}" + (" ⚠️" if chain_state["error"] else ""))
header_cols[2].markdown(f"RFQ: {format_age(rfq_state['ts'])}" + (" ⚠️" if rfq_state["error"] else ""))
if header_cols[3].button("\U0001F504 Refresh"):
    st.session_state.force_refresh = True
    st.rerun()

if chain_value["block_number"] is not None:
    st.caption(f"chain read at block {chain_value['block_number']}")

for label, state in (("Signed quotes", quotes_state), ("Chain sweep", chain_state), ("RFQ", rfq_state)):
    if state["error"]:
        st.warning(f"{label} fetch failed, showing last good data: {state['error']}")

st.divider()


# --- Summary row ---

live_rows = [r for r in rows if r.state == "live"]
needs_quote_rows = [r for r in rows if r.state == "needs_quote"]

summary_cols = st.columns(4)
summary_cols[0].metric("Tokens quoted", f"{len(live_rows)}/{len(rows)}")
summary_cols[1].metric("\U0001F534 Need a quote" if needs_quote_rows else "Need a quote", len(needs_quote_rows))
summary_cols[2].metric("Live capacity (USDC)", f"{sum(r.capacity_usdc for r in live_rows):,.0f}")
if live_rows:
    soonest = min(live_rows, key=lambda r: r.binding_quote.deadline)
    summary_cols[3].metric("First to mature", model.format_countdown(soonest.binding_quote.deadline), soonest.symbol)
else:
    summary_cols[3].metric("First to mature", "—")

st.divider()


# --- Token cards ---

def logo_or_chip(symbol: str):
    url = LOGOS.get(symbol.upper())
    if url:
        st.image(url, width=40)
    else:
        st.markdown(
            f"<div style='width:40px;height:40px;border-radius:50%;background:#444;"
            f"color:#fff;display:flex;align-items:center;justify-content:center;"
            f"font-size:14px;font-weight:600;'>{symbol[:2].upper()}</div>",
            unsafe_allow_html=True,
        )


def render_card(row: model.TokenRow):
    label, color = model.STATE_LABELS[row.state]
    with st.container(border=True):
        top = st.columns([1, 5])
        with top[0]:
            logo_or_chip(row.symbol)
        with top[1]:
            st.markdown(f"**{row.symbol}** — {row.name}")
            if row.closing_soon:
                st.markdown(f":orange[**CLOSING SOON**]")
            else:
                st.markdown(f":{color}[**{label}**]")

        bq = row.binding_quote
        if bq:
            st.markdown(f"### {bq.discount_pct:.2f}%")
            st.caption(f"{bq.discount_ppm} ppm · floor {model.ppm_to_pct_str(row.floor_ppm)}")

            st.markdown(f"matures in **{model.format_countdown(bq.deadline)}**")
            if bq.signed_at:
                total = bq.deadline - bq.signed_at.timestamp()
                elapsed = model.now_ts() - bq.signed_at.timestamp()
                st.progress(min(max(elapsed / total, 0.0), 1.0) if total > 0 else 1.0)

            open_q = row.open_quotes
            if len(open_q) > 1:
                st.caption("Ladder (binding quote first):")
                for q in sorted(open_q, key=lambda q: (q.discount_ppm, q.deadline)):
                    marker = "→ binds" if q is bq else "takes over after"
                    st.caption(f"- {q.discount_pct:.2f}% until {model.format_countdown(q.deadline)} ({marker})")

            st.markdown(f"[Safe message](https://app.safe.global/transactions/msg?safe=eth:{SAFE}&messageHash={bq.message_hash})")
        else:
            st.markdown(f"floor {model.ppm_to_pct_str(row.floor_ppm)} · no open quote")

        guard = f"max {row.limit_usdc:,.0f} USDC · floor {model.ppm_to_pct_str(row.floor_ppm)}"
        if row.market_liquidity_usdc is not None:
            guard += f" · market sees {row.market_liquidity_usdc:,.0f} USDC"
            if row.guard_mismatch:
                guard += " ⚠️ guard/market disagree"
        st.caption(guard)


card_cols = st.columns(2)
for i, row in enumerate(rows):
    with card_cols[i % 2]:
        render_card(row)

st.divider()


# --- RFQ section ---

st.subheader("Symbiotic RFQ")

st.markdown("**Market-visible liquidity vs our guard**")
st.dataframe(
    [
        {
            "Token": r.symbol,
            "Market-visible liquidity (USDC)": r.market_liquidity_usdc,
            "Our limit (USDC)": r.limit_usdc,
            "Current headroom (USDC)": r.capacity_usdc,
        }
        for r in rows
    ],
    use_container_width=True,
    hide_index=True,
)

st.markdown("**Recent fills**")
roster_decimals = {r.address.lower(): r.decimals for r in rows}
roster_symbols = {r.address.lower(): r.symbol for r in rows}
live_symbols = {r.symbol for r in live_rows}

# Fills aren't limited to roster tokens - look up decimals for anything else on-chain
# rather than guessing, since a wrong decimals count silently produces a plausible-looking
# wrong rate (exactly the failure mode this whole app exists to avoid, see BUILD spec §8).
if "token_meta_cache" not in st.session_state:
    st.session_state.token_meta_cache = {}

unknown_tokens = {
    o.get("input", {}).get("token", "").lower()
    for o in rfq_value["orders"][:25]
    if o.get("input", {}).get("token") and o["input"]["token"].lower() not in roster_decimals
    and o["input"]["token"].lower() not in st.session_state.token_meta_cache
}
if unknown_tokens:
    w3 = chain.get_web3()
    for addr in unknown_tokens:
        try:
            symbol, _name, decimals = chain.fetch_erc20_meta(w3, addr)
            st.session_state.token_meta_cache[addr] = (symbol, decimals)
        except Exception:
            st.session_state.token_meta_cache[addr] = (None, None)

fill_rows = []
for o in rfq_value["orders"][:25]:
    inp = o.get("input", {})
    outs = o.get("outputs", [])
    out = outs[0] if outs else {}
    in_token = inp.get("token", "")
    in_token_lower = in_token.lower()
    out_decimals = 6  # settlement leg is USDC in every case documented in §4.3

    if in_token_lower in roster_decimals:
        in_symbol = roster_symbols[in_token_lower]
        in_decimals = roster_decimals[in_token_lower]
    else:
        in_symbol, in_decimals = st.session_state.token_meta_cache.get(in_token_lower, (None, None))
        in_symbol = in_symbol or in_token[:10]

    try:
        in_amount = int(inp.get("amount", 0)) / (10**in_decimals) if in_decimals is not None else None
        out_amount = int(out.get("amount", 0)) / (10**out_decimals)
        rate = out_amount / in_amount if in_amount else None
    except (ValueError, ZeroDivisionError):
        in_amount, out_amount, rate = None, None, None
    fill_rows.append(
        {
            "Token in": in_symbol,
            "Amount in": in_amount,
            "USDC out": out_amount,
            "Rate (USDC/token)": rate,
            "Matches a live quote": "✓" if in_symbol in live_symbols else "",
            "Swapper": o.get("swapper", "")[:10],
            "Tx": o.get("txHash", ""),
        }
    )

st.dataframe(fill_rows, use_container_width=True, hide_index=True)

st.divider()


# --- History ---

with st.expander("Full signing history"):
    history_rows = []
    for r in rows:
        for q in r.quotes:
            history_rows.append(
                {
                    "Token": r.symbol,
                    "Discount": f"{q.discount_pct:.2f}%",
                    "Floor at signing vs now": model.ppm_to_pct_str(r.floor_ppm),
                    "Maturity": model.format_countdown(q.deadline) if q.deadline > model.now_ts() else "past",
                    "State": q.status_label,
                    "Signed": q.signed_at.strftime("%Y-%m-%d %H:%M UTC") if q.signed_at else "—",
                    "Message": f"https://app.safe.global/transactions/msg?safe=eth:{SAFE}&messageHash={q.message_hash}",
                }
            )
    st.dataframe(history_rows, use_container_width=True, hide_index=True)


# --- Footnotes ---

st.divider()
st.markdown(
    """
**How to read this page**

- `discount` is parts per million, not basis points. `30000` = 3.00%.
- `minDiscount` (the floor) is checked at swap time, not signing time - a quote below the
  current floor is signed but dead, and shows as such above rather than as live.
- A signed quote is a **standing policy, not a one-shot fill**: it can be redeemed repeatedly,
  at any size, until its deadline, bounded only by the limit and vault capacity. With several
  live quotes on one token, the shallowest discount always binds.
- **`isUsedNonce == true` means the quote was revoked**, not that it was redeemed or filled.
"""
)
