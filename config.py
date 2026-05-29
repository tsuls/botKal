import os
from dotenv import load_dotenv

load_dotenv()

# --- API ---
KALSHI_API_KEY_ID = os.getenv("KALSHI_API_KEY_ID", "")
KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "./kalshi_private_key.pem")
KALSHI_REST_BASE = "https://api.kalshi.com/trade-api/v2"
KALSHI_WS_URL = "wss://api.kalshi.com/trade-api/ws/v2"
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"

# --- Trading mode ---
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # "paper" or "live"
LIVE = TRADING_MODE == "live"

# --- Position sizing ---
MAX_TRADE_USD = float(os.getenv("MAX_TRADE_USD", "20"))
BANKROLL = float(os.getenv("BANKROLL", "500"))
KELLY_FRACTION = 0.25  # quarter-Kelly

# --- Signal thresholds (tune after paper mode) ---
YES_PRICE_MIN = 75.0        # only watch contracts where Yes >= 75¢
YES_PRICE_MAX = 97.0        # ignore near-certain contracts (no room to collapse)
VELOCITY_THRESHOLD = -0.3   # cents/sec — must be declining at least this fast
BTC_MOMENTUM_THRESHOLD = 0.15  # % move in 60s considered significant
MIN_CONFIDENCE = 0.65
SECONDS_WINDOW_MIN = 10     # don't enter with less than 10s left
SECONDS_WINDOW_MAX = 120    # only act in last 2 minutes

# --- Exit thresholds ---
TAKE_PROFIT_PCT = 0.40      # exit when No position gains 40%
STOP_LOSS_PCT = 0.25        # exit when No position loses 25%
EXPIRY_CUTOFF_SECONDS = 8   # if < 8s left when signal fires, let ride to settlement

# --- Order book ---
LIMIT_ORDER_SLIPPAGE_CENTS = 2  # bid this many cents above current No ask

# --- Database ---
DB_PATH = "kalshi_bot.db"
