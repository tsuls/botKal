# Kalshi Flip Bot — Project Context

## What This Project Is
A Python trading bot targeting **late-contract probability flips** on Kalshi's 15-minute Bitcoin price markets.

The core strategy: in the last 1–2 minutes of a contract, detect when a high-confidence Yes side (90%+) is collapsing — and buy the cheap No contracts (trading at ~10¢) before the flip completes. Target 5–40% intra-contract gains. Never hold a directional bias to expiry.

---

## Strategy Logic

### The Flip Signal
A genuine late-flip has a fingerprint across three simultaneous data streams:

1. **Kalshi price velocity** — Yes probability dropping faster than baseline (>0.3¢/sec decline)
2. **BTC spot momentum** — price moving *against* the contract's current lean on Binance
3. **Order book asymmetry** — No ask getting eaten, Yes bid thinning, spread widening

All three aligning in the last 2 minutes = flip candidate.

### Entry Conditions
- Yes price between 75–97 (overconfident side, room to collapse)
- Velocity < -0.3¢/sec sustained over ~10 seconds
- BTC moving adversely vs. contract strike
- 10–120 seconds remaining
- Composite confidence score > 0.65

### Exit Conditions
- Take profit: No price up 40% from entry
- Stop loss: No price down 25% from entry
- Held to expiry if <8 seconds remaining when signal fires

### Position Sizing
- Max 2% of bankroll per flip trade
- Hard cap $20–50 per trade (thin late-contract liquidity)
- Use **limit orders**, not market — bid 1–2¢ above ask on No
- Quarter-Kelly sizing once model is calibrated

---

## Tech Stack
- **Language:** Python 3.11+
- **Async:** `asyncio` + `websockets`
- **HTTP:** `httpx`
- **Data:** `sqlite3` (built-in) for logging + backtesting
- **BTC feed:** Binance public WebSocket (no auth needed)
- **Config:** `.env` file via `python-dotenv`

---

## Project Structure
```
kalshi-bot/
├── CLAUDE.md              # This file
├── .env                   # API keys (never commit)
├── .gitignore
├── requirements.txt
├── config.py              # Thresholds, limits, constants
├── client.py              # Kalshi REST wrapper (auth, orders, portfolio)
├── feed.py                # WebSocket feed: Kalshi prices + Binance BTC
├── signals.py             # FlipDetector class — core signal engine
├── order_manager.py       # Entry/exit/position tracking
├── store.py               # SQLite schema + logging
├── main.py                # Orchestrator — wires everything together
└── backtest.py            # Replay stored data against signal engine
```

---

## Key Classes & Files

### `signals.py` — FlipDetector
- Maintains 90s rolling window of Kalshi Yes prices
- Maintains 60s rolling window of BTC spot prices
- `update(yes_price, btc_price, seconds_remaining)` → returns `FlipSignal` or `None`
- Composite confidence score weighted: velocity (40%), BTC momentum (35%), urgency (15%), overconfidence (10%)

### `feed.py` — WebSocket Feed
- Connects to `wss://api.kalshi.com/trade-api/ws/v2` for order book + price ticks
- Connects to Binance public WS for BTC/USDT spot
- Pipes both into `FlipDetector.update()` on every tick
- Reconnects automatically on drop

### `client.py` — Kalshi REST Client
- Base URL: `https://api.kalshi.com/trade-api/v2`
- Auth: API key ID + private key from `.env`
- Methods: `place_order()`, `cancel_order()`, `get_positions()`, `get_balance()`
- Always use **limit orders** for No side entries

---

## API Details
- **Kalshi REST:** `https://api.kalshi.com/trade-api/v2`
- **Kalshi WS:** `wss://api.kalshi.com/trade-api/ws/v2`
- **Binance BTC WS:** `wss://stream.binance.com:9443/ws/btcusdt@trade`
- API keys from: Kalshi dashboard → Settings → API

---

## Important Constraints
- **Never market-buy No contracts** — liquidity is thin in last 2 min, use limit orders
- **Hard position cap:** $20–50 per trade regardless of Kelly output
- **Paper trade first** — log every signal for 2–3 weeks before live execution
- **Kill switch:** a `HALT` flag file in project root; `main.py` checks every loop
- **Never commit `.env`**

---

## Current Status
- [ ] Project scaffolded
- [ ] `.env` and API keys configured
- [ ] `feed.py` running
- [ ] `store.py` logging ticks
- [ ] `signals.py` paper mode active
- [ ] Signal logs reviewed and thresholds tuned
- [ ] Live trading enabled (small size)
