import sqlite3
import time
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                yes_bid REAL,
                yes_ask REAL,
                no_bid REAL,
                no_ask REAL,
                btc_price REAL,
                seconds_remaining INTEGER,
                settled INTEGER  -- NULL until expiry, then 0 (No wins) or 1 (Yes wins)
            );

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                market_id TEXT NOT NULL,
                yes_prob REAL,
                prob_velocity REAL,
                btc_momentum REAL,
                seconds_remaining INTEGER,
                confidence REAL,
                mode TEXT NOT NULL,  -- 'paper' or 'live'
                entry_price REAL,
                exit_price REAL,
                pnl_pct REAL,
                exit_reason TEXT     -- 'take_profit', 'stop_loss', 'expiry'
            );

            CREATE INDEX IF NOT EXISTS idx_ticks_market ON ticks(market_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_signals_market ON signals(market_id, timestamp);
        """)


def log_tick(market_id: str, yes_bid: float, yes_ask: float,
             no_bid: float, no_ask: float, btc_price: float,
             seconds_remaining: int):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO ticks
               (market_id, timestamp, yes_bid, yes_ask, no_bid, no_ask, btc_price, seconds_remaining)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (market_id, int(time.time()), yes_bid, yes_ask,
             no_bid, no_ask, btc_price, seconds_remaining)
        )


def log_signal(market_id: str, yes_prob: float, prob_velocity: float,
               btc_momentum: float, seconds_remaining: int, confidence: float,
               mode: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (timestamp, market_id, yes_prob, prob_velocity, btc_momentum,
                seconds_remaining, confidence, mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (int(time.time()), market_id, yes_prob, prob_velocity,
             btc_momentum, seconds_remaining, confidence, mode)
        )
        return cur.lastrowid


def update_signal_trade(signal_id: int, entry_price: float, exit_price: float,
                        pnl_pct: float, exit_reason: str):
    with get_conn() as conn:
        conn.execute(
            """UPDATE signals
               SET entry_price=?, exit_price=?, pnl_pct=?, exit_reason=?
               WHERE id=?""",
            (entry_price, exit_price, pnl_pct, exit_reason, signal_id)
        )


def mark_tick_settled(market_id: str, yes_won: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE ticks SET settled=? WHERE market_id=? AND settled IS NULL",
            (1 if yes_won else 0, market_id)
        )


def recent_ticks(market_id: str, seconds: int = 120) -> list:
    cutoff = int(time.time()) - seconds
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM ticks WHERE market_id=? AND timestamp>=? ORDER BY timestamp",
            (market_id, cutoff)
        ).fetchall()
