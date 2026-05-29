import asyncio
import logging
import os
import time
from pathlib import Path

from config import LIVE
from client import KalshiClient
from feed import run_feeds
from signals import FlipDetector
from order_manager import OrderManager
from store import init_db, log_tick

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

HALT_FILE = Path("HALT")

# Per-market detectors and the shared order manager
_detectors: dict[str, FlipDetector] = {}
_order_manager: OrderManager = None


def _seconds_remaining(market: dict) -> int:
    """Estimate seconds until market close from Kalshi market data."""
    close_time = market.get("close_time", "")
    if not close_time:
        return 999
    from datetime import datetime, timezone
    try:
        close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
        delta = (close_dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(delta))
    except Exception:
        return 999


def on_tick(ticker: str, tick: dict, btc_price: float):
    """Called on every Kalshi orderbook update."""
    if HALT_FILE.exists():
        return

    yes_mid = tick.get("yes_mid")
    no_mid = tick.get("no_mid")
    seconds = tick.get("seconds_remaining", 999)

    if yes_mid is None or no_mid is None:
        return

    # Log raw tick to SQLite
    log_tick(
        market_id=ticker,
        yes_bid=tick.get("yes_bid") or 0,
        yes_ask=tick.get("yes_ask") or 0,
        no_bid=100 - (tick.get("yes_ask") or 100),
        no_ask=100 - (tick.get("yes_bid") or 0),
        btc_price=btc_price,
        seconds_remaining=seconds,
    )

    # Initialise detector for new markets
    if ticker not in _detectors:
        _detectors[ticker] = FlipDetector(market_id=ticker)

    detector = _detectors[ticker]
    signal = detector.update(yes_mid, btc_price, seconds)

    if signal:
        no_ask = 100 - (tick.get("yes_bid") or yes_mid)
        asyncio.create_task(_order_manager.enter(signal, no_ask))

    # Update any open position for this market
    if _order_manager.has_position(ticker):
        asyncio.create_task(
            _order_manager.update_position(ticker, no_mid, seconds)
        )


async def market_refresh_loop(client: KalshiClient, interval: int = 60):
    """Periodically refresh the list of active BTC markets."""
    global _detectors
    while True:
        if HALT_FILE.exists():
            logger.warning("HALT file detected — shutting down")
            _order_manager.cancel_all()
            break
        try:
            markets = client.get_active_btc_markets()
            tickers = [m["ticker"] for m in markets]
            logger.info(f"Active BTC markets: {tickers}")
            # Inject seconds_remaining into feed for existing ticks
            for m in markets:
                t = m["ticker"]
                if t in _detectors:
                    # Detectors persist; seconds_remaining comes from WS tick data
                    pass
        except Exception as e:
            logger.error(f"Market refresh error: {e}")
        await asyncio.sleep(interval)


async def main():
    global _order_manager

    init_db()

    mode = "LIVE" if LIVE else "PAPER"
    logger.info(f"=== Kalshi Flip Bot starting — mode: {mode} ===")

    client = KalshiClient() if LIVE else None
    _order_manager = OrderManager(client=client)

    if LIVE:
        bal = client.get_balance()
        logger.info(f"Account balance: ${bal:.2f}")
        markets = client.get_active_btc_markets()
    else:
        # In paper mode we still need tickers — fetch anonymously
        try:
            temp_client = KalshiClient()
            markets = temp_client.get_active_btc_markets()
            temp_client.close()
        except Exception:
            logger.warning("Could not fetch markets (no API keys yet?) — using empty list")
            markets = []

    tickers = [m["ticker"] for m in markets]
    logger.info(f"Watching {len(tickers)} markets: {tickers}")

    tasks = [run_feeds(tickers, on_tick)]
    if LIVE:
        tasks.append(market_refresh_loop(client))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
