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
        # Kalshi's 15-min BTC series ticker — verify at:
        # https://api.kalshi.com/trade-api/v2/series and look for BTC 15-min
        # Common values seen: "KXBTC", "BTCX" — update BTC_SERIES below if wrong
        BTC_SERIES = "KXBTC"
        data = self._get("/markets", params={
            "status": "open",
            "series_ticker": BTC_SERIES,
            "limit": 100,
        })
        markets = data.get("markets", [])

        # Filter to 15-minute duration markets only (exclude hourly/daily)
        # Kalshi market titles typically say "15-minute" or have a 15-min window
        fifteen_min = [
            m for m in markets
            if _is_15min_market(m)
        ]

        if not fifteen_min:
            # Fallback: return all BTC markets so you can inspect what's available
            import logging
            logging.getLogger(__name__).warning(
                f"No 15-min markets found under series '{BTC_SERIES}'. "
                f"Got {len(markets)} total markets. Check series ticker. "
                f"Tickers: {[m.get('ticker') for m in markets[:5]]}"
            )
            return sorted(markets, key=lambda m: m.get("close_time", ""))

        return sorted(fifteen_min, key=lambda m: m.get("close_time", ""))


def _is_15min_market(market: dict) -> bool:
    """Detect 15-minute BTC markets by title or ticker pattern."""
    title = (market.get("title") or "").lower()
    subtitle = (market.get("subtitle") or "").lower()
    ticker = (market.get("ticker") or "").lower()

    if "15" in title or "15-min" in title or "15 min" in title:
        return True
    if "15" in subtitle:
        return True
    # Kalshi tickers for 15-min often end in HH:MM with 15-min intervals
    # e.g. KXBTC-25MAY2906:15 vs KXBTC-25MAY29 (daily)
    if ":" in ticker:
        return True
    return False

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
