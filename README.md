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

## Deploy (KPK Railway, per the Vibe Coded Apps Guidelines)

This repo ships as a Docker container so it can run as its own service in the shared KPK Labs
Railway project, reachable internally over Twingate rather than a public URL:

```bash
docker build -t symbiotic-quotes .
docker run -p 8501:8501 -e PORT=8501 -e KPKUSERNAME=... -e KPKPASSWORD=... symbiotic-quotes
```

On Railway: connect this repo, set `KPKUSERNAME` / `KPKPASSWORD` in the service's Variables (never
in the repo), and auto-deploy from `main` - engineering handles the Twingate-internal domain. Ask in
#curation or ping João for the initial Railway hookup.

### Alternative: Streamlit Community Cloud

Works too if you'd rather not wait on the Railway hookup, but it requires the repo to be public and
Streamlit's GitHub App to be approved for the `kpk-labs` org - the thing that's currently stuck.
1. Deploy from the Streamlit Cloud dashboard, pointing at `app.py`.
2. In the app's Secrets (TOML, so values need quotes):
   ```toml
   KPKUSERNAME = "..."
   KPKPASSWORD = "..."
   ```

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
