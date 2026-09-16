# Build spec — KPK Symbiotic LL quotes (Streamlit)

A read-only dashboard showing which tokens on the Symbiotic **Liquid Lane** adapter currently carry a
discount quote signed by the kpk curator Safe, how deep, when each matures, and the guard rails that
bound them. Plus a view on the Symbiotic RFQ side: liquidity the market can draw, and recent fills.

Target: **Python + Streamlit**, deployed to Streamlit Community Cloud. Single app, no database, no
background jobs. Every number comes from a public API or an Ethereum RPC call at request time.

Everything in this document was verified live on **16 Sep 2026** unless marked TODO.

---

## 1. Why this exists (read before designing)

An earlier version baked its data in at publish time and went stale, which is the whole problem being
solved. **Nothing here should be cached longer than a minute or two, and the UI must always state how
old its data is.** A page that looks current but isn't is worse than no page.

Audience: kpk contributors, not just the curator. They open the link, read the state, and leave. No
logins, no buttons they must press to get correct data, no per-user setup.

---

## 2. Constants

```python
CHAIN_ID  = 1  # Ethereum mainnet
SAFE      = "0x73af5fcdF830035401e00c322D657982b4a71288"  # kpk curator Safe
ADAPTER   = "0x97c0baefcf688a8389108a0893144ae0a1408b3a"  # LiquidLaneAdapter (MigratableEntityProxy)
ADAPTER_IMPL = "0xc41b9c2300E444d7031EBDe8aE24e40C268FaE91"  # verified source lives here
VAULT     = "0x8bcd746976885b5832bad07b4921e3f2dd1d3703"
ASSET     = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC, 6 decimals — vault asset
PROTOCOL  = "0x1ad7dde8c93f41ca717f8ee74295f9325293a94b"  # counterparty in every signed quote
RPC       = "https://ethereum-rpc.publicnode.com"          # public, no key, verified working
```

Read `VAULT` / `ASSET` from the contract rather than hardcoding if you prefer — `adapter.vault()` then
`vault.asset()` — but the values above are current.

---

## 3. Domain semantics — get these right, they are not obvious

Read from the verified implementation source. Do not re-derive.

**`discount` is parts per million.** `DISCOUNT_PRECISION = 10**6`. Payout is
`amountOut * (1e6 - discount) / 1e6`. So `30000` = 3.00%, `600` = 0.06%. It is *not* basis points —
getting this wrong makes a 3% quote look like 300%.

**`minDiscount[token]`** (ppm) is the floor, and it is checked **at swap time**, not at signing time.
Raising the floor therefore invalidates any live quote below the new floor. Display it next to every
quote.

**`limit[token]`** is the vault-funded asset cap **denominated in USDC**, not in the redeemed token.
The contract enforces
`IAccount(accounts[t]).totalAssets() + tokenOutToAllocate > limit[t] → revert LimitExceeded()`.
Live headroom is `getMaxAssets(token)`.

**`deadline`** is a `uint48` unix timestamp. Past it the swap reverts regardless of anything else.

### ⚠ The one that trips everyone up

**A signed Discount is a standing policy, not a one-shot fill.** The `swap()` function *checks*
`isUsedNonce[token][nonce]` but **never sets it**. Only `invalidateNonce()` writes that mapping. The
EIP-712 typehash comment in the source says so outright: "reusable signed discount policies".

Consequences you must reflect in the UI:

- One signature can be redeemed **repeatedly**, at **any size** (`amountIn` is a free call argument),
  until its deadline, bounded only by `limit` and vault capacity.
- With several quotes live on one token, the counterparty picks per swap, so the **shallowest discount
  binds every time**. A deeper quote signed later does nothing until the shallow one expires. Where a
  token has more than one live quote, show the ladder and mark which one binds.
- **`isUsedNonce == true` means REVOKED, not redeemed.** Never label it "used" or "filled".

A quote is **open** iff `deadline > now` **and** `isUsedNonce == False`.

---

## 4. Data sources

### 4.1 Signed quotes — Safe Transaction Service

```
GET https://safe-transaction-mainnet.safe.global/api/v1/safes/{SAFE}/messages/?limit=100
```

No authentication. CORS-open. Verified returning 200 with 11 messages.

Rate limits for unauthenticated use are **2 requests/second and 5,000 per month**
(https://docs.safe.global/core-api/how-to-use-api-keys). With server-side caching (§6) that is not a
concern. If you ever hit it, a free Safe API key raises the ceiling — put it in `st.secrets`, never in
the repo.

Response shape (trimmed to what matters):

```json
{
  "count": 11,
  "results": [{
    "messageHash": "0xac98810c...",
    "created":  "2026-09-10T15:47:57.748406Z",
    "modified": "2026-09-10T15:51:27.258772Z",
    "confirmations": [{"owner": "0xF0Cf...", "signature": "0x...", "signatureType": "EOA"}],
    "proposedBy": "0xF0Cf1e3Ec6264b03241826f5b2aBda17B4352A75",
    "message": {
      "domain": {"name": "LiquidLaneAdapter", "version": "1", "chainId": 1,
                 "verifyingContract": "0x97c0baefcf688a8389108a0893144ae0a1408b3a"},
      "primaryType": "Discount",
      "message": {
        "tokenToRedeem": "0x7433806912eae67919e66aea853d46fa0aef98a8",
        "discount": "30000",
        "signer":   "0x73af5fcdf830035401e00c322d657982b4a71288",
        "protocol": "0x1ad7dde8c93f41ca717f8ee74295f9325293a94b",
        "nonce":    "1039430538165744098335910637364769227989194959270738589615896676684938505173 62",
        "deadline": 1790264868
      }
    }
  }]
}
```

Filter to `m["message"]["primaryType"] == "Discount"`. `modified` is the fully-signed timestamp — use
it as "signed at". `len(confirmations)` is the signature count (2-of-2 today).

Deep link to one message:
`https://app.safe.global/transactions/msg?safe=eth:{SAFE}&messageHash={messageHash}`

### 4.2 On-chain state — Ethereum RPC

`https://ethereum-rpc.publicnode.com`, no key, verified. **Do not use `eth.blockscout.com` for RPC** —
it 429s after a handful of `eth_call`s.

Use `web3.py` with these ABI fragments on `ADAPTER`:

```python
ADAPTER_ABI = [
  {"name":"getTokensToRedeemLength","inputs":[],"outputs":[{"type":"uint256"}],
   "stateMutability":"view","type":"function"},
  {"name":"tokensToRedeem","inputs":[{"type":"uint256"}],"outputs":[{"type":"address"}],
   "stateMutability":"view","type":"function"},
  {"name":"limit","inputs":[{"type":"address"}],"outputs":[{"type":"uint256"}],
   "stateMutability":"view","type":"function"},
  {"name":"minDiscount","inputs":[{"type":"address"}],"outputs":[{"type":"uint256"}],
   "stateMutability":"view","type":"function"},
  {"name":"accounts","inputs":[{"type":"address"}],"outputs":[{"type":"address"}],
   "stateMutability":"view","type":"function"},
  {"name":"isUsedNonce","inputs":[{"type":"address"},{"type":"uint256"}],"outputs":[{"type":"bool"}],
   "stateMutability":"view","type":"function"},
  {"name":"getMaxAssets","inputs":[{"type":"address"}],"outputs":[{"type":"uint256"}],
   "stateMutability":"nonpayable","type":"function"},
  {"name":"vault","inputs":[],"outputs":[{"type":"address"}],
   "stateMutability":"view","type":"function"}
]
```

`getMaxAssets` is declared non-view but is safe to read with `.call()` — it does not write.

Per-token account balance deployed against a token: `IAccount(accounts[token]).totalAssets()`
(`totalAssets()` returns `uint256`, USDC units). Token metadata via standard ERC-20
`symbol()` / `name()` / `decimals()`.

Raw selectors, if you skip web3.py:

| call | selector |
|---|---|
| `getTokensToRedeemLength()` | `0x55d931bf` |
| `tokensToRedeem(uint256)` | `0x3d2a61ce` |
| `limit(address)` | `0xd8797262` |
| `minDiscount(address)` | `0xd9104c14` |
| `accounts(address)` | `0x5e5c06e2` |
| `getMaxAssets(address)` | `0x22135549` |
| `isUsedNonce(address,uint256)` | `0x0ee60fa7` |
| `vault()` / `asset()` / `totalAssets()` | `0xfbfa77cf` / `0x38d52e0f` / `0x01e1d114` |
| `symbol()` / `decimals()` / `name()` | `0x95d89b41` / `0x313ce567` / `0x06fdde03` |

Relevant events, if you ever want history: `SetLimit(address indexed tokenToRedeem, uint256)` topic0
`0x195f01c216465063f9e6a5cc900b834b284e36961065b3d5f63b115ecd88582a`, and
`SetMinDiscount(address indexed tokenToRedeem, uint256)` topic0
`0xd842ee806832c3e5f5e97d22f096a87f9042e992a2d37a2b14077a81804d5ff7`.

### 4.3 Symbiotic RFQ — `swap.symbiotic.fi`

Same API the public Liquid Lane UI calls. Unauthenticated, CORS-open, verified.

**Liquidity the market can draw for a token:**

```
POST https://swap.symbiotic.fi/api/v1/liquidity
{"tokenIn": "<token address>", "chainId": 1}
```

```json
{"tokenIn":"0x8c213ee7...","tokenOut":"0xa0b86991...",
 "tokenInInfo":{"address":"0x8c21...","symbol":"JTRSY","name":"Janus Henderson Treasury Fund","decimals":6},
 "tokenOutInfo":{"address":"0xa0b8...","symbol":"USDC","name":"USD Coin","decimals":6},
 "totalLiquidity":"200000000000",
 "solvers":[{"solverId":"symbiotic_third","liquidity":"200000000000"}]}
```

`totalLiquidity` is in USDC base units (6 dp) → 200,000 USDC, which is **exactly** `limit[JTRSY]`.
Showing our guard next to what the market sees is one of the more valuable things this app can do: if
they ever disagree, something is misconfigured.

> **TODO before labelling anything "ours":** confirm whether `solverId: "symbiotic_third"` is kpk
> specifically or several curators aggregated. Until that is known, label the column
> "market-visible liquidity", not "our liquidity".

**Recent fills:**

```
GET https://swap.symbiotic.fi/api/v1/orders?orderStatus=filled
```

Requires at least one of `orderId`, `orderIds`, `orderHash`, `orderHashes`, `orderStatus`, `swapper`,
`filler` — a bare call 400s with that message.

```json
{"requestId":"6f4e16ba-...",
 "orders":[{"type":"Priority","orderId":"9331926e-...","orderStatus":"filled",
   "quoteId":"0c5adb9d-...","swapper":"0x638cc048...",
   "txHash":"0x8009ccfe...","nonce":"745770599...",
   "input":{"token":"0x19ebb352...","amount":"18485078"},
   "outputs":[{"token":"0xa0b86991...","recipient":"0x638cc048...","amount":"19563994"}],
   "settledAmounts":[{"token":"0xa0b86991...","amount":"19563994",
                      "recipient":"0x638cc048...","txHash":"0x8009ccfe..."}]}]}
```

Amounts are base units of their respective tokens — divide by that token's decimals. Effective rate is
`output_amount / input_amount` adjusted for decimals; compare it against the quoted discount for the
same token to sanity-check.

Also documented but **not verified by me** — probe before relying on them:
`POST /api/v1/quote`, `POST /api/v1/discount`, `POST /api/v1/check_approval`, `GET /api/v1/health`.
Docs: https://docs.symbiotic.fi/liquid-lane/api

---

## 5. Derived model

Build one record per token on the adapter roster (`tokensToRedeem`), **not** one per quote — a token
with no quote is the actionable case and must be visible.

```python
@dataclass
class TokenRow:
    address: str
    symbol: str
    name: str
    decimals: int
    limit_usdc: float          # limit[token] / 1e6
    floor_ppm: int             # minDiscount[token]
    deployed_usdc: float       # IAccount(accounts[token]).totalAssets() / 1e6
    capacity_usdc: float       # getMaxAssets(token) / 1e6
    market_liquidity_usdc: float | None   # Symbiotic /liquidity, None if the call failed
    quotes: list[Quote]        # every signed quote for this token, newest deadline first

@dataclass
class Quote:
    message_hash: str
    discount_ppm: int
    deadline: int              # unix
    signed_at: datetime
    signers: int
    nonce: str
    revoked: bool              # isUsedNonce — REVOKED, not redeemed
```

Per-token state, in priority order:

| state | condition | label | colour |
|---|---|---|---|
| `live` | ≥1 open quote | **LIVE**, or **CLOSING SOON** within 72h of the binding quote's deadline | green / amber |
| `needs_quote` | no open quote **and** `limit > 0` | **SIGN A QUOTE** | red |
| `no_capacity` | `limit == 0` and the token has past quotes | **NO CAPACITY** | grey |
| `not_enabled` | `limit == 0` and no quote ever signed | **NOT ENABLED** — not whitelisted on the vault yet | grey |

The **binding quote** for a live token is `min(open_quotes, key=lambda q: (q.discount_ppm, q.deadline))`
— see §3. Sort tokens `needs_quote` first, then `live` by soonest deadline, then the greyed ones.

### Current roster (16 Sep 2026) — use as fixtures

| token | address | limit (USDC) | floor | live quote |
|---|---|---|---|---|
| JAAA | `0x5a0f93d040de44e78f251b03c43be9cf317dcf64` | 150,000 | 0.05% | 0.06%, matures 24 Sep |
| JTRSY | `0x8c213ee79581ff4984583c6a801e5263418c4b86` | 200,000 | 0.05% | 0.06%, matures 24 Sep |
| mF-ONE | `0x238a700ed6165261cf8b2e544ba797bc11e466ba` | 50,000 | 2.50% | 2.50%, matures 24 Sep |
| mGLOBAL | `0x7433806912eae67919e66aea853d46fa0aef98a8` | 50,000 | 3.00% | 3.00%, matures 24 Sep |
| deJAAA | `0xaaa0008c8cf3a7dca931adaf04336a5d808c82cc` | 0 | 0.05% | — |
| deJTRSY | `0xa6233014b9b7aaa74f38fa1977ffc7a89642dc72` | 0 | 0.05% | — |
| HYBOND | `0x1204371ac0e5176f4b8c5b2f16c2bec551b6fc1a` | 0 | 0.00% | never quoted |
| AA_FalconXUSDC | `0xc26a6fa2c37b38e549a4a1807543801db684f99c` | 0 | 0.00% | never quoted |

11 quotes signed to date, none revoked. The five older JTRSY quotes at 0.01–0.02% were signed *below*
the current 0.05% floor and would revert at swap time — a useful edge case to render sensibly in the
history table.

---

## 6. Caching and freshness

- Wrap each fetch in `st.cache_data(ttl=60)` — Safe messages, the on-chain sweep, and the RFQ calls as
  three separate cached functions so one failing source doesn't blank the others.
- A **Refresh** button in the header calls `st.cache_data.clear()` then `st.rerun()`.
- Header must always show the age of each source, e.g. `quotes 40s ago · chain 40s ago · RFQ 40s ago`,
  plus the block number the chain reads came from.
- If a source fails, keep the last good values, mark that section stale with the error, and let the
  rest of the page render. Never blank the page on one failed call.
- Optional: auto-refresh with `st.fragment(run_every="60s")` on the header fragment. Check this against
  the Streamlit version you pin — the fragment API has moved around. A manual button is an acceptable
  fallback; do not add a third-party autorefresh package just for this.

---

## 7. UI

Single page, top to bottom. Wide layout.

**Header** — title, the Safe and adapter addresses (monospace, linked to Etherscan), the three
freshness clocks, block number, Refresh button.

**Summary row** — `st.columns(4)` with `st.metric`:
- Tokens quoted, e.g. `4/8`
- Need a quote (red when > 0)
- Live capacity, sum of `capacity_usdc` over live tokens, in USDC
- First to mature, a countdown to the soonest binding deadline

**Token cards** — two per row (`st.columns(2)`), one per token, in the sort order from §5. Each shows:
- logo + symbol + full name, status pill
- **discount** of the binding quote, large, with `{ppm} ppm · floor {floor}` underneath
- **matures in** as `8d 02h`, with the absolute datetime underneath
- a progress bar for time remaining between signing and deadline
- if more than one open quote: the ladder, marking which binds and what takes over when it expires
- guard line: `max {limit} USDC · floor {floor}% · market sees {market_liquidity} USDC`, flagged if
  guard and market liquidity disagree
- link to the Safe message

Cards are the right call over a dataframe here: this is scanned, not sorted. Keep `st.dataframe` for
the history.

**RFQ section** — two parts:
- a table of per-token market-visible liquidity vs our limit vs current headroom
- recent fills: token in, amount, USDC out, effective rate, swapper, tx link. Highlight fills whose
  effective discount is close to a quote we have live.

**History** — `st.expander("Full signing history")` with a dataframe of all quotes: token, discount,
maturity, state (Active / Matured / Revoked), signed date, message link.

**Footnotes** — the semantics from §3, especially the reusable-quote behaviour. Contributors reading
this page need it to interpret what they see.

### Token logos

Direct URLs, already verified from Blockscout token metadata:

```python
LOGOS = {
 "MGLOBAL": "https://assets.coingecko.com/coins/images/102172980/small/mglobal-Cm4yjVTI.png?1776956923",
 "MF-ONE":  "https://assets.coingecko.com/coins/images/66975/small/mfone-logo.png?1751307469",
 "JTRSY":   "https://assets.coingecko.com/coins/images/70445/small/JTRSY.png?1762078582",
 "JAAA":    "https://assets.coingecko.com/coins/images/70446/small/jaaa.png?1762078666",
 "DEJTRSY": "https://assets.coingecko.com/coins/images/102175872/small/Centrifuge_Token_from_SVG_to_PNG.png?1787820266",
 "DEJAAA":  "https://assets.coingecko.com/coins/images/102172528/small/deJAAA.png?1773764620",
}
```

Match case-insensitively — the on-chain symbols are `mGLOBAL`, `mF-ONE`, `deJAAA`, `deJTRSY`. No logo
for HYBOND or AA_FalconXUSDC yet; fall back to a coloured initials chip so new tokens always render.
(Jerry also has issuer-level marks — one Janus Henderson logo for JAAA + JTRSY, one deRWA mark for the
de-tokens — if he prefers those to per-token art; ask him.)

---

## 8. Project layout

```
quote-board/
├── app.py                 # Streamlit entry point, UI only
├── src/
│   ├── safe.py            # Safe Transaction Service client
│   ├── chain.py            # web3 reads: roster, guards, capacity, revocations
│   ├── rfq.py              # Symbiotic liquidity + orders
│   └── model.py            # TokenRow / Quote, state derivation, formatting
├── tests/
│   └── test_model.py      # state machine + ppm/decimal maths against §5 fixtures
├── requirements.txt
├── .streamlit/config.toml
└── README.md
```

```
# requirements.txt
streamlit>=1.40
requests>=2.32
web3>=7.0
```

Pin exact versions once it runs. Keep all formatting (ppm → %, base units → human, unix → countdown) in
`model.py` so it's unit-testable without a network.

**Tests matter more than usual here** — the ppm conversion and the open/revoked logic are exactly the
places a silent error produces a plausible-looking wrong number. Use the §5 table as fixtures.

---

## 9. Deployment (Streamlit Community Cloud)

- Public GitHub repo, `app.py` at the root, deploy from the Streamlit Cloud dashboard.
- No secrets are required — every source is public and unauthenticated. If a Safe API key is added
  later, it goes in `st.secrets`, never the repo.
- Free-tier apps sleep when idle and cold-start on first visit. That's fine for this use, but tell the
  team the first load can take a few seconds.
- Streamlit Cloud can restrict viewers by email if this should not be public. Nothing on the page is
  secret — it's all public chain state and Safe's public API — so that's a preference, not a
  requirement.

---

## 10. Build order

1. `src/safe.py` + `src/chain.py`, driven from a throwaway script printing the §5 table. Confirm the
   numbers match before any UI exists.
2. `src/model.py` + tests. Get the state machine and ppm maths right.
3. `app.py` — header, summary, token cards. Ship at this point; it's already more useful than what
   exists.
4. `src/rfq.py` + the RFQ section.
5. Polish: history expander, footnotes, auto-refresh.

---

## 11. Known gotchas

- `eth.blockscout.com` 429s under a few `eth_call`s. Use `ethereum-rpc.publicnode.com`.
  `eth.llamarpc.com` was CORS/network-blocked in testing; `rpc.ankr.com/eth` now requires auth.
- The adapter is a proxy — verified source is on the implementation (`ADAPTER_IMPL`), all calls go to
  the proxy address.
- The roster changes: AA_FalconXUSDC appeared between 15 and 16 Sep. Always read `tokensToRedeem`
  rather than hardcoding the token list.
- `nonce` values exceed 2^53 — keep them as strings in Python and never let them touch a float or JS
  number.
- A quote below the current floor is signed-but-dead. Show it as such rather than as live.
- Don't say "redeemed" anywhere. `isUsedNonce` means revoked (§3).
