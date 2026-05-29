import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config import (
    TAKE_PROFIT_PCT, STOP_LOSS_PCT, EXPIRY_CUTOFF_SECONDS,
    MAX_TRADE_USD, BANKROLL, KELLY_FRACTION,
    LIMIT_ORDER_SLIPPAGE_CENTS, LIVE,
)
from signals import FlipSignal
from store import log_signal, update_signal_trade

logger = logging.getLogger(__name__)


@dataclass
class OpenPosition:
    signal_id: int
    market_id: str
    entry_price_cents: float    # No price at entry
    contracts: int
    order_id: Optional[str]
    entered_at: float = field(default_factory=time.time)


class OrderManager:
    def __init__(self, client=None):
        self._client = client   # KalshiClient — None in paper mode
        self._positions: dict[str, OpenPosition] = {}  # market_id -> position

    def has_position(self, market_id: str) -> bool:
        return market_id in self._positions

    async def enter(self, signal: FlipSignal, current_no_ask_cents: float) -> bool:
        """
        Try to enter a No position based on the flip signal.
        Returns True if position was opened.
        """
        if self.has_position(signal.market_id):
            logger.debug(f"Already in {signal.market_id}, skipping")
            return False

        if signal.seconds_remaining < EXPIRY_CUTOFF_SECONDS:
            logger.info(f"Too close to expiry ({signal.seconds_remaining}s), skipping")
            return False

        no_ask = current_no_ask_cents
        limit_price = int(no_ask + LIMIT_ORDER_SLIPPAGE_CENTS)
        limit_price = max(1, min(99, limit_price))

        dollars = min(MAX_TRADE_USD, BANKROLL * 0.02)
        contracts = int(dollars / (limit_price / 100))
        if contracts < 1:
            logger.warning("Position size rounds to 0 contracts, skipping")
            return False

        mode = "live" if LIVE else "paper"
        signal_id = log_signal(
            market_id=signal.market_id,
            yes_prob=signal.yes_prob,
            prob_velocity=signal.prob_velocity,
            btc_momentum=signal.btc_momentum,
            seconds_remaining=signal.seconds_remaining,
            confidence=signal.confidence,
            mode=mode,
        )

        if LIVE and self._client:
            try:
                order = self._client.place_limit_order(
                    ticker=signal.market_id,
                    side="no",
                    count=contracts,
                    limit_price_cents=limit_price,
                )
                order_id = order.get("order", {}).get("order_id")
                logger.info(
                    f"[LIVE] Placed No order on {signal.market_id}: "
                    f"{contracts} contracts @ {limit_price}¢ | confidence={signal.confidence:.2f}"
                )
            except Exception as e:
                logger.error(f"Order placement failed: {e}")
                return False
        else:
            order_id = f"paper-{signal_id}"
            logger.info(
                f"[PAPER] Signal on {signal.market_id}: "
                f"Yes={signal.yes_prob:.1f}¢ velocity={signal.prob_velocity:.3f}¢/s "
                f"btc_mom={signal.btc_momentum:.3f}% "
                f"confidence={signal.confidence:.2f} "
                f"would buy {contracts} No @ {limit_price}¢"
            )

        self._positions[signal.market_id] = OpenPosition(
            signal_id=signal_id,
            market_id=signal.market_id,
            entry_price_cents=limit_price,
            contracts=contracts,
            order_id=order_id,
        )
        return True

    async def update_position(self, market_id: str, current_no_price: float,
                              seconds_remaining: int):
        """Check exit conditions for an open position."""
        pos = self._positions.get(market_id)
        if not pos:
            return

        pnl_pct = (current_no_price - pos.entry_price_cents) / pos.entry_price_cents

        exit_reason = None
        if pnl_pct >= TAKE_PROFIT_PCT:
            exit_reason = "take_profit"
        elif pnl_pct <= -STOP_LOSS_PCT:
            exit_reason = "stop_loss"
        elif seconds_remaining <= EXPIRY_CUTOFF_SECONDS:
            exit_reason = "expiry"

        if exit_reason:
            await self._exit(pos, current_no_price, pnl_pct, exit_reason)

    async def _exit(self, pos: OpenPosition, exit_price: float,
                    pnl_pct: float, reason: str):
        logger.info(
            f"[{'LIVE' if LIVE else 'PAPER'}] Exit {pos.market_id} "
            f"reason={reason} pnl={pnl_pct:+.1%} "
            f"entry={pos.entry_price_cents:.1f}¢ exit={exit_price:.1f}¢"
        )

        if LIVE and self._client:
            try:
                # Sell No = buy Yes
                self._client.place_limit_order(
                    ticker=pos.market_id,
                    side="yes",
                    count=pos.contracts,
                    limit_price_cents=int(100 - exit_price - LIMIT_ORDER_SLIPPAGE_CENTS),
                )
            except Exception as e:
                logger.error(f"Exit order failed: {e}")

        update_signal_trade(
            signal_id=pos.signal_id,
            entry_price=pos.entry_price_cents,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        )
        del self._positions[pos.market_id]

    def cancel_all(self):
        """Emergency halt — cancel all open orders."""
        if LIVE and self._client:
            self._client.cancel_all_orders()
        self._positions.clear()
        logger.warning("All positions cleared (kill switch)")
