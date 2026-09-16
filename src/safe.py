import requests

from .config import SAFE, SAFE_API


def fetch_discount_messages(limit: int = 100, timeout: int = 10) -> list[dict]:
    """All Safe Transaction Service messages for SAFE whose primaryType is Discount.

    No auth, CORS-open. Paginates via the API's own `next` link in case the
    signed-quote count ever grows past one page.
    """
    messages: list[dict] = []
    url = f"{SAFE_API}/safes/{SAFE}/messages/"
    params = {"limit": limit}

    while url:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        messages.extend(data.get("results", []))
        url = data.get("next")
        params = None  # `next` is already a full URL with its own query string

    return [m for m in messages if m.get("message", {}).get("primaryType") == "Discount"]
