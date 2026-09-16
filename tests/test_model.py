"""Tests for the ppm maths and open/revoked state machine - the two places
a silent error produces a plausible-looking wrong number (see BUILD spec §3, §8).

No pytest required: `python tests/test_model.py` runs everything directly.
Fixtures below mirror the roster table in BUILD-quote-board-streamlit.md §5.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model import Quote, TokenRow, build_rows, now_ts, sort_key  # noqa: E402

FAR_FUTURE = int(now_ts()) + 30 * 86400
PAST = int(now_ts()) - 86400


def make_quote(discount_ppm=30000, deadline=FAR_FUTURE, revoked=False, nonce="1"):
    return Quote(
        message_hash=f"0x{nonce}",
        discount_ppm=discount_ppm,
        deadline=deadline,
        signed_at=None,
        signers=2,
        nonce=nonce,
        revoked=revoked,
    )


def make_row(limit_usdc=0, quotes=None):
    return TokenRow(
        address="0xTOKEN",
        symbol="TEST",
        name="Test Token",
        decimals=18,
        limit_usdc=limit_usdc,
        floor_ppm=5000,
        deployed_usdc=0,
        capacity_usdc=limit_usdc,
        market_liquidity_usdc=None,
        quotes=quotes or [],
    )


def test_ppm_is_not_bips():
    # 30000 ppm must read as 3.00%, never 300% (bips) or 0.03% (raw fraction).
    q = make_quote(discount_ppm=30000)
    assert abs(q.discount_pct - 3.00) < 1e-9

    q = make_quote(discount_ppm=600)
    assert abs(q.discount_pct - 0.06) < 1e-9


def test_open_requires_future_deadline_and_not_revoked():
    assert make_quote(deadline=FAR_FUTURE, revoked=False).is_open is True
    assert make_quote(deadline=PAST, revoked=False).is_open is False
    assert make_quote(deadline=FAR_FUTURE, revoked=True).is_open is False


def test_revoked_is_not_labelled_used_or_filled():
    q = make_quote(revoked=True)
    assert q.status_label == "Revoked"
    assert "used" not in q.status_label.lower()
    assert "filled" not in q.status_label.lower()


def test_shallowest_discount_binds():
    shallow = make_quote(discount_ppm=600, deadline=FAR_FUTURE, nonce="a")
    deep = make_quote(discount_ppm=30000, deadline=FAR_FUTURE, nonce="b")
    row = make_row(limit_usdc=100, quotes=[shallow, deep])
    assert row.binding_quote is shallow


def test_state_live_requires_open_quote():
    row = make_row(limit_usdc=100, quotes=[make_quote(deadline=FAR_FUTURE)])
    assert row.state == "live"


def test_state_needs_quote_when_capacity_but_no_open_quote():
    row = make_row(limit_usdc=100, quotes=[])
    assert row.state == "needs_quote"


def test_state_no_capacity_when_limit_zero_but_has_past_quote():
    row = make_row(limit_usdc=0, quotes=[make_quote(deadline=PAST)])
    assert row.state == "no_capacity"


def test_state_not_enabled_when_never_quoted_and_no_limit():
    row = make_row(limit_usdc=0, quotes=[])
    assert row.state == "not_enabled"


def test_quote_below_current_floor_still_open_but_flagged_by_caller():
    # is_open only checks deadline/revocation - the floor check is the caller's
    # job (swap-time enforcement), so a stale-floor quote must still show as open.
    q = make_quote(discount_ppm=100, deadline=FAR_FUTURE)
    row = make_row(limit_usdc=100, quotes=[q])
    assert row.state == "live"
    assert row.floor_ppm == 5000  # floor now above the quote's discount


def test_sort_order_needs_quote_before_live_before_greyed_out():
    needs_quote = make_row(limit_usdc=100, quotes=[])
    live = make_row(limit_usdc=100, quotes=[make_quote(deadline=FAR_FUTURE)])
    not_enabled = make_row(limit_usdc=0, quotes=[])
    ordered = sorted([live, not_enabled, needs_quote], key=sort_key)
    assert [r.state for r in ordered] == ["needs_quote", "live", "not_enabled"]


def test_build_rows_matches_on_lowercased_address_and_strips_nonce_whitespace():
    chain_tokens = [
        {"address": "0xAbC0000000000000000000000000000000000A", "symbol": "AAA", "name": "AAA",
         "decimals": 18, "limit": 100_000_000, "floor_ppm": 5000, "deployed": 0, "capacity": 100_000_000}
    ]
    quotes_raw = [
        {
            "messageHash": "0xhash1",
            "modified": "2026-09-10T15:51:27.258772Z",
            "confirmations": [{"owner": "0x1"}, {"owner": "0x2"}],
            "message": {
                "message": {
                    "tokenToRedeem": "0xabc0000000000000000000000000000000000a",
                    "discount": "30000",
                    "nonce": "123 456",  # spec's example shows a stray embedded space
                    "deadline": FAR_FUTURE,
                }
            },
        }
    ]
    revocations = {("0xabc0000000000000000000000000000000000a", "123456"): False}
    rows = build_rows(chain_tokens, quotes_raw, revocations, {})
    assert len(rows) == 1
    assert rows[0].state == "live"
    assert rows[0].binding_quote.discount_pct == 3.0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    if failures:
        print(f"\n{failures} failure(s)")
        sys.exit(1)
    print("\nAll tests passed")
