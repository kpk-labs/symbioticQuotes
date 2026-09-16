"""Domain model: token roster state + signed-quote maths.

Kept dependency-free (no requests/web3 imports) so tests/test_model.py can
exercise the ppm conversion and open/revoked state machine without a network.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

DISCOUNT_PRECISION = 10**6


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class Quote:
    message_hash: str
    discount_ppm: int
    deadline: int  # unix
    signed_at: datetime | None
    signers: int
    nonce: str
    revoked: bool  # isUsedNonce - REVOKED, never "used"/"filled"

    @property
    def is_open(self) -> bool:
        return (not self.revoked) and self.deadline > now_ts()

    @property
    def discount_pct(self) -> float:
        return self.discount_ppm / DISCOUNT_PRECISION * 100

    @property
    def status_label(self) -> str:
        if self.revoked:
            return "Revoked"
        if self.deadline <= now_ts():
            return "Matured"
        return "Active"


@dataclass
class TokenRow:
    address: str
    symbol: str
    name: str
    decimals: int
    limit_usdc: float
    floor_ppm: int
    deployed_usdc: float
    capacity_usdc: float
    market_liquidity_usdc: float | None
    quotes: list[Quote] = field(default_factory=list)

    @property
    def open_quotes(self) -> list[Quote]:
        return [q for q in self.quotes if q.is_open]

    @property
    def binding_quote(self) -> Quote | None:
        """The quote that actually fills: shallowest discount wins, deadline breaks ties."""
        open_q = self.open_quotes
        if not open_q:
            return None
        return min(open_q, key=lambda q: (q.discount_ppm, q.deadline))

    @property
    def state(self) -> str:
        if self.binding_quote is not None:
            return "live"
        if self.limit_usdc > 0:
            return "needs_quote"
        if self.quotes:
            return "no_capacity"
        return "not_enabled"

    @property
    def closing_soon(self) -> bool:
        bq = self.binding_quote
        return bool(bq) and (bq.deadline - now_ts()) <= 72 * 3600

    @property
    def guard_mismatch(self) -> bool:
        """Flag when our on-chain limit and what the market reports disagree."""
        if self.market_liquidity_usdc is None:
            return False
        if self.limit_usdc == 0:
            return self.market_liquidity_usdc > 0
        diff = abs(self.market_liquidity_usdc - self.limit_usdc) / self.limit_usdc
        return diff > 0.01


STATE_LABELS = {
    "live": ("LIVE", "green"),
    "needs_quote": ("SIGN A QUOTE", "red"),
    "no_capacity": ("NO CAPACITY", "gray"),
    "not_enabled": ("NOT ENABLED", "gray"),
}

_STATE_ORDER = {"needs_quote": 0, "live": 1, "no_capacity": 2, "not_enabled": 2}


def sort_key(row: TokenRow):
    if row.state == "live":
        return (_STATE_ORDER["live"], row.binding_quote.deadline)
    return (_STATE_ORDER[row.state], row.symbol)


def format_countdown(deadline: int) -> str:
    delta = deadline - now_ts()
    if delta <= 0:
        return "expired"
    days = int(delta // 86400)
    hours = int((delta % 86400) // 3600)
    return f"{days}d {hours:02d}h"


def ppm_to_pct_str(ppm: int) -> str:
    return f"{ppm / DISCOUNT_PRECISION * 100:.2f}%"


def build_rows(
    chain_tokens: list[dict],
    quotes_raw: list[dict],
    revocations: dict[tuple[str, str], bool],
    rfq_liquidity: dict[str, float],
) -> list[TokenRow]:
    """Combine the three raw sources into one TokenRow per roster entry.

    One row per token on the roster, not per quote - a token with no quote is
    the actionable case and must show up.
    """
    quotes_by_token: dict[str, list[Quote]] = defaultdict(list)
    for m in quotes_raw:
        msg = m["message"]["message"]
        token = msg["tokenToRedeem"].lower()
        nonce = str(msg["nonce"]).replace(" ", "")
        quotes_by_token[token].append(
            Quote(
                message_hash=m["messageHash"],
                discount_ppm=int(msg["discount"]),
                deadline=int(msg["deadline"]),
                signed_at=parse_iso(m.get("modified")),
                signers=len(m.get("confirmations") or []),
                nonce=nonce,
                revoked=revocations.get((token, nonce), False),
            )
        )

    rows = []
    for t in chain_tokens:
        addr_lower = t["address"].lower()
        quotes = sorted(quotes_by_token.get(addr_lower, []), key=lambda q: -q.deadline)
        rows.append(
            TokenRow(
                address=t["address"],
                symbol=t["symbol"],
                name=t["name"],
                decimals=t["decimals"],
                limit_usdc=t["limit"] / 1e6,
                floor_ppm=t["floor_ppm"],
                deployed_usdc=t["deployed"] / 1e6,
                capacity_usdc=t["capacity"] / 1e6,
                market_liquidity_usdc=rfq_liquidity.get(addr_lower),
                quotes=quotes,
            )
        )

    rows.sort(key=sort_key)
    return rows
