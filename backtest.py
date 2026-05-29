"""
Replay stored ticks against the FlipDetector to evaluate signal quality.

Usage:
    python backtest.py [--days 30] [--min-confidence 0.65]

Output:
    - Signal accuracy (how many flip signals preceded actual flips)
    - P&L distribution assuming 40% TP / 25% SL exits
    - Suggested threshold adjustments
"""

import argparse
import sqlite3
from collections import defaultdict

from config import DB_PATH, TAKE_PROFIT_PCT, STOP_LOSS_PCT
from signals import FlipDetector


def load_ticks(days: int) -> list:
    import time
    cutoff = int(time.time()) - days * 86400
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM ticks WHERE timestamp >= ? ORDER BY market_id, timestamp",
            (cutoff,)
        ).fetchall()


def run(days: int = 30, min_confidence: float = 0.65):
    ticks = load_ticks(days)
    if not ticks:
        print("No ticks in database yet. Run main.py in paper mode first.")
        return

    print(f"Loaded {len(ticks)} ticks over last {days} days")

    # Group by market
    by_market: dict[str, list] = defaultdict(list)
    for t in ticks:
        by_market[t["market_id"]].append(t)

    total_signals = 0
    correct_flips = 0  # signal fired and Yes eventually lost (settled=0)
    simulated_pnl = []

    for market_id, market_ticks in by_market.items():
        detector = FlipDetector(market_id=market_id)
        settled = None
        for t in market_ticks:
            if t["settled"] is not None:
                settled = t["settled"]

        if settled is None:
            continue  # market not yet settled, skip

        yes_won = bool(settled)

        for t in market_ticks:
            signal = detector.update(
                yes_price=t["yes_ask"] or 0,
                btc_price=t["btc_price"] or 0,
                seconds_remaining=t["seconds_remaining"] or 999,
            )
            if signal and signal.confidence >= min_confidence:
                total_signals += 1
                # A flip signal predicts Yes will lose → No wins
                if not yes_won:
                    correct_flips += 1
                    simulated_pnl.append(TAKE_PROFIT_PCT)
                else:
                    simulated_pnl.append(-STOP_LOSS_PCT)

    if total_signals == 0:
        print("No signals fired. Try lowering --min-confidence.")
        return

    accuracy = correct_flips / total_signals
    avg_pnl = sum(simulated_pnl) / len(simulated_pnl)
    win_count = sum(1 for p in simulated_pnl if p > 0)

    print(f"\n=== Backtest Results ({days} days, confidence >= {min_confidence}) ===")
    print(f"  Total signals fired : {total_signals}")
    print(f"  Correct flips       : {correct_flips} ({accuracy:.1%})")
    print(f"  Win rate            : {win_count}/{total_signals} ({win_count/total_signals:.1%})")
    print(f"  Avg simulated P&L   : {avg_pnl:+.1%} per trade")
    print(f"  Break-even accuracy : ~57% (40% TP / 25% SL)")
    print()
    if accuracy >= 0.57:
        print("  Edge appears positive. Consider going live at small size.")
    else:
        print("  Accuracy below break-even. Tighten thresholds before going live.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    args = parser.parse_args()
    run(days=args.days, min_confidence=args.min_confidence)
