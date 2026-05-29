import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import KALSHI_REST_BASE, KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH


def _load_private_key():
    path = Path(KALSHI_PRIVATE_KEY_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Private key not found at {KALSHI_PRIVATE_KEY_PATH}. "
            "Download it from Kalshi dashboard -> Settings -> API."
        )
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _sign(method: str, path: str, timestamp_ms: int) -> str:
    """RSA-PSS signature required by Kalshi API v2."""
    private_key = _load_private_key()
    message = f"{timestamp_ms}{method}{path}".encode()
    sig = private_key.sign(message, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.DIGEST_LENGTH,
    ), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _auth_headers(method: str, path: str) -> dict:
    ts = int(time.time() * 1000)
    return {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": str(ts),
        "KALSHI-ACCESS-SIGNATURE": _sign(method.upper(), path, ts),
        "Content-Type": "application/json",
    }


class KalshiClient:
    def __init__(self):
        self._http = httpx.Client(base_url=KALSHI_REST_BASE, timeout=10.0)

    def _get(self, path: str, params: dict = None):
        headers = _auth_headers("GET", f"/trade-api/v2{path}")
        r = self._http.get(path, headers=headers, params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict):
        headers = _auth_headers("POST", f"/trade-api/v2{path}")
        r = self._http.post(path, headers=headers, content=json.dumps(body))
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str):
        headers = _auth_headers("DELETE", f"/trade-api/v2{path}")
        r = self._http.delete(path, headers=headers)
        r.raise_for_status()
        return r.json()

    # --- Account ---

    def get_balance(self) -> float:
        """Returns available balance in dollars."""
        data = self._get("/portfolio/balance")
        return data["balance"] / 100  # Kalshi returns cents

    def get_positions(self) -> list:
        return self._get("/portfolio/positions").get("market_positions", [])

    # --- Market data ---

    def get_market(self, ticker: str) -> dict:
        return self._get(f"/markets/{ticker}")

    def get_orderbook(self, ticker: str, depth: int = 5) -> dict:
        return self._get(f"/markets/{ticker}/orderbook", params={"depth": depth})

    def get_active_btc_markets(self) -> list:
        """Fetch open 15-min BTC markets sorted by close time."""
        data = self._get("/markets", params={
            "status": "open",
            "series_ticker": "KXBTC",
            "limit": 20,
        })
        markets = data.get("markets", [])
        return sorted(markets, key=lambda m: m.get("close_time", ""))

    # --- Orders ---

    def place_limit_order(self, ticker: str, side: str, count: int,
                          limit_price_cents: int) -> dict:
        """
        side: 'yes' or 'no'
        count: number of contracts
        limit_price_cents: limit price in cents (1–99)
        """
        body = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "type": "limit",
            "count": count,
            "yes_price": limit_price_cents if side == "yes" else 100 - limit_price_cents,
        }
        return self._post("/portfolio/orders", body)

    def cancel_order(self, order_id: str) -> dict:
        return self._delete(f"/portfolio/orders/{order_id}")

    def cancel_all_orders(self):
        orders = self._get("/portfolio/orders", params={"status": "resting"})
        for o in orders.get("orders", []):
            try:
                self.cancel_order(o["order_id"])
            except Exception as e:
                print(f"Failed to cancel {o['order_id']}: {e}")

    def get_order(self, order_id: str) -> dict:
        return self._get(f"/portfolio/orders/{order_id}")

    def close(self):
        self._http.close()
