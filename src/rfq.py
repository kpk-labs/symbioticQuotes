import requests

from .config import CHAIN_ID, RFQ_API


def fetch_liquidity(token_address: str, timeout: int = 10) -> dict | None:
    """Market-visible liquidity for a token, per the Symbiotic RFQ API.

    Returns None on any failure so a single bad token doesn't break the sweep -
    callers should treat None as "unknown", not "zero".
    """
    try:
        resp = requests.post(
            f"{RFQ_API}/liquidity",
            json={"tokenIn": token_address, "chainId": CHAIN_ID},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def fetch_filled_orders(timeout: int = 10) -> list[dict]:
    try:
        resp = requests.get(
            f"{RFQ_API}/orders",
            params={"orderStatus": "filled"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("orders", [])
    except requests.RequestException:
        return []
