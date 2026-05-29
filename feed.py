import asyncio
import json
import logging
import time
from typing import Callable, Optional

import websockets

from config import KALSHI_WS_URL, BINANCE_WS_URL

logger = logging.getLogger(__name__)

# Shared state — updated by each WS handler, read by the main loop
_btc_price: float = 0.0
_market_ticks: dict[str, dict] = {}  # ticker -> latest tick


def get_btc_price() -> float:
    return _btc_price


def get_market_tick(ticker: str) -> Optional[dict]:
    return _market_ticks.get(ticker)


async def binance_feed():
    """Streams BTC/USDT trades from Binance and updates _btc_price."""
    global _btc_price
    backoff = 1
    while True:
        try:
            async with websockets.connect(BINANCE_WS_URL, ping_interval=20) as ws:
                backoff = 1
                logger.info("Binance WS connected")
                async for raw in ws:
                    msg = json.loads(raw)
                    _btc_price = float(msg["p"])
        except Exception as e:
            logger.warning(f"Binance WS error: {e} — reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def kalshi_feed(tickers: list[str],
                      on_tick: Callable[[str, dict, float], None]):
    """
    Streams orderbook updates for the given Kalshi tickers.
    Calls on_tick(ticker, tick_data, btc_price) on each update.
    """
    backoff = 1
    while True:
        try:
            async with websockets.connect(KALSHI_WS_URL, ping_interval=20) as ws:
                backoff = 1
                logger.info(f"Kalshi WS connected, subscribing to {tickers}")

                # Subscribe to orderbook delta feed for each ticker
                sub_msg = {
                    "id": 1,
                    "cmd": "subscribe",
                    "params": {
                        "channels": ["orderbook_delta"],
                        "market_tickers": tickers,
                    }
                }
                await ws.send(json.dumps(sub_msg))

                async for raw in ws:
                    msg = json.loads(raw)
                    _handle_kalshi_msg(msg, on_tick)

        except Exception as e:
            logger.warning(f"Kalshi WS error: {e} — reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


def _handle_kalshi_msg(msg: dict, on_tick: Callable):
    msg_type = msg.get("type")
    if msg_type not in ("orderbook_snapshot", "orderbook_delta"):
        return

    ticker = msg.get("msg", {}).get("market_ticker", "")
    if not ticker:
        return

    data = msg.get("msg", {})
    tick = _parse_tick(ticker, data)
    if tick:
        _market_ticks[ticker] = tick
        on_tick(ticker, tick, _btc_price)


def _parse_tick(ticker: str, data: dict) -> Optional[dict]:
    """Extract best bid/ask for Yes and No from orderbook data."""
    try:
        yes_bids = data.get("yes", [])    # list of [price, size]
        yes_asks = data.get("no", [])     # Kalshi: No bids = Yes asks

        yes_bid = float(yes_bids[0][0]) if yes_bids else None
        yes_ask = float(yes_asks[0][0]) if yes_asks else None

        if yes_bid is None and yes_ask is None:
            return None

        yes_mid = (yes_bid + yes_ask) / 2 if (yes_bid and yes_ask) else (yes_bid or yes_ask)
        no_mid = 100 - yes_mid if yes_mid else None

        return {
            "ticker": ticker,
            "timestamp": int(time.time()),
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "yes_mid": yes_mid,
            "no_mid": no_mid,
            "btc_price": _btc_price,
        }
    except (IndexError, TypeError, ValueError):
        return None


async def run_feeds(tickers: list[str], on_tick: Callable):
    """Launch Binance and Kalshi feeds concurrently."""
    await asyncio.gather(
        binance_feed(),
        kalshi_feed(tickers, on_tick),
    )
