# KPK symbiotic quotes

Read-only dashboard for the Symbiotic Liquid Lane adapter: which tokens carry a live discount
quote signed by the kpk curator Safe, how deep, when each matures, and the guard rails around
them, plus market-visible liquidity and recent fills from Symbiotic RFQ.

No database, no background jobs - every number comes from the Safe Transaction Service, an
Ethereum RPC call, or the Symbiotic RFQ API at request time, cached for 60 seconds. See
`BUILD-quote-board-streamlit.md` for the full spec and domain semantics (read this before
touching `src/model.py` - the ppm/reusable-quote rules there are easy to get subtly wrong).

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set KPKUSERNAME / KPKPASSWORD
streamlit run app.py
```

## Tests

```bash
python tests/test_model.py
```

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub (already at `kpk-labs/symbioticQuotes`), `app.py` at the root.
2. Deploy from the Streamlit Cloud dashboard, pointing at `app.py`.
3. In the app's Secrets, set:
   ```toml
   KPKUSERNAME = "..."
   KPKPASSWORD = "..."
   ```
4. Restrict viewers by email in Streamlit Cloud if this shouldn't be publicly reachable - nothing
   on the page is secret (all sources are public), so that's a preference, not a requirement.

## Layout

```
app.py                 # UI + fetch orchestration, login gate
src/
  config.py            # addresses, ABIs, logos
  safe.py              # Safe Transaction Service client
  chain.py             # web3 reads: roster, guards, capacity, revocations
  rfq.py               # Symbiotic liquidity + filled orders
  model.py             # TokenRow / Quote, state derivation, formatting
  util.py              # TTL cache with last-good-value fallback
tests/
  test_model.py         # ppm maths + state machine, no network required
```
