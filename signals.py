import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from config import (
    YES_PRICE_MIN, YES_PRICE_MAX, VELOCITY_THRESHOLD,
    BTC_MOMENTUM_THRESHOLD, MIN_CONFIDENCE,
    SECONDS_WINDOW_MIN, SECONDS_WINDOW_MAX,
)


@dataclass
class FlipSignal:
    market_id: str
    yes_prob: float
    prob_velocity: float    # cents/sec, negative = collapsing
    btc_momentum: float     # % change in BTC over last 60s
    seconds_remaining: int
    confidence: float       # 0.0–1.0


@dataclass
class FlipDetector:
    market_id: str
    # Rolling windows of (timestamp, value)
    _price_history: deque = field(default_factory=lambda: deque(maxlen=90))
    _btc_history: deque = field(default_factory=lambda: deque(maxlen=60))

    def update(self, yes_price: float, btc_price: float,
               seconds_remaining: int) -> Optional[FlipSignal]:
        now = time.time()
        self._price_history.append((now, yes_price))
        self._btc_history.append((now, btc_price))
        return self._evaluate(yes_price, seconds_remaining)

    def _evaluate(self, yes_price: float, seconds_remaining: int) -> Optional[FlipSignal]:
        if not (SECONDS_WINDOW_MIN <= seconds_remaining <= SECONDS_WINDOW_MAX):
            return None
        if not (YES_PRICE_MIN <= yes_price <= YES_PRICE_MAX):
            return None

        velocity = self._price_velocity()
        btc_momentum = self._btc_momentum()

        if velocity >= VELOCITY_THRESHOLD:
            return None

        if not self._btc_adverse(btc_momentum):
            return None

        confidence = self._score(velocity, btc_momentum, yes_price, seconds_remaining)
        if confidence < MIN_CONFIDENCE:
            return None

        return FlipSignal(
            market_id=self.market_id,
            yes_prob=yes_price,
            prob_velocity=velocity,
            btc_momentum=btc_momentum,
            seconds_remaining=seconds_remaining,
            confidence=confidence,
        )

    def _price_velocity(self) -> float:
        """Returns cents/sec change in Yes price over last 10 data points."""
        if len(self._price_history) < 10:
            return 0.0
        recent = list(self._price_history)[-10:]
        dt = recent[-1][0] - recent[0][0]
        dp = recent[-1][1] - recent[0][1]
        return dp / dt if dt > 0 else 0.0

    def _btc_momentum(self) -> float:
        """Returns % change in BTC price over the rolling 60s window."""
        if len(self._btc_history) < 2:
            return 0.0
        prices = [p for _, p in self._btc_history]
        return (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] else 0.0

    def _btc_adverse(self, momentum: float) -> bool:
        """True if BTC is moving against the contract's current bias."""
        # For a "Yes = BTC up" contract: adverse BTC move is downward
        # We use a simple threshold; tune after paper mode data
        return abs(momentum) >= BTC_MOMENTUM_THRESHOLD

    def _score(self, velocity: float, btc_momentum: float,
               yes_price: float, seconds_remaining: int) -> float:
        v_score = min(abs(velocity) / 1.0, 1.0)
        btc_score = min(abs(btc_momentum) / 0.3, 1.0)
        urgency = 1.0 - (seconds_remaining / SECONDS_WINDOW_MAX)
        overconfidence = (yes_price - YES_PRICE_MIN) / (YES_PRICE_MAX - YES_PRICE_MIN)

        return (
            v_score * 0.40
            + btc_score * 0.35
            + urgency * 0.15
            + overconfidence * 0.10
        )
