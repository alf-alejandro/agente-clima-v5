"""trend_tracker.py — Price history and uptrend detection for V5.

Same logic as V2 but tracking YES prices instead of NO prices.
Entry allowed when last TREND_MIN_OBSERVATIONS YES prices are
monotonically increasing AND total rise >= TREND_MIN_RISE.
"""

import threading
import logging
from datetime import datetime, timezone

from app.config import TREND_MIN_RISE, TREND_MIN_OBSERVATIONS, PRICE_HISTORY_TTL

log = logging.getLogger(__name__)

MAX_HISTORY_PER_MARKET = 50


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


class TrendTracker:
    def __init__(self):
        self._history: dict[str, list[tuple[float, float]]] = {}  # {cid: [(ts, yes_price), ...]}
        self._lock = threading.Lock()

    def record(self, condition_id: str, yes_price: float):
        """Add a CLOB YES price observation for a market."""
        ts = _now_ts()
        with self._lock:
            if condition_id not in self._history:
                self._history[condition_id] = []
            hist = self._history[condition_id]
            hist.append((ts, yes_price))
            if len(hist) > MAX_HISTORY_PER_MARKET:
                self._history[condition_id] = hist[-MAX_HISTORY_PER_MARKET:]

    def has_uptrend(self, condition_id: str) -> bool:
        """True if last TREND_MIN_OBSERVATIONS YES prices are strictly increasing
        and total rise >= TREND_MIN_RISE."""
        with self._lock:
            hist = self._history.get(condition_id, [])

        if len(hist) < TREND_MIN_OBSERVATIONS:
            return False

        window = [price for _, price in hist[-TREND_MIN_OBSERVATIONS:]]

        for i in range(1, len(window)):
            if window[i] <= window[i - 1]:
                return False

        return (window[-1] - window[0]) >= TREND_MIN_RISE

    def observation_count(self, condition_id: str) -> int:
        with self._lock:
            return len(self._history.get(condition_id, []))

    def all_tracked(self) -> dict[str, dict]:
        result = {}
        with self._lock:
            for cid, hist in self._history.items():
                if not hist:
                    continue
                prices = [p for _, p in hist]
                result[cid] = {
                    "observations": len(hist),
                    "first_price": round(prices[0], 4),
                    "last_price": round(prices[-1], 4),
                    "total_rise": round(prices[-1] - prices[0], 4),
                    "has_uptrend": self._check_uptrend(hist),
                }
        return result

    def _check_uptrend(self, hist):
        if len(hist) < TREND_MIN_OBSERVATIONS:
            return False
        window = [price for _, price in hist[-TREND_MIN_OBSERVATIONS:]]
        for i in range(1, len(window)):
            if window[i] <= window[i - 1]:
                return False
        return (window[-1] - window[0]) >= TREND_MIN_RISE

    def purge_old(self):
        cutoff = _now_ts() - PRICE_HISTORY_TTL
        with self._lock:
            to_delete = [
                cid for cid, hist in self._history.items()
                if hist and hist[-1][0] < cutoff
            ]
            for cid in to_delete:
                del self._history[cid]
        if to_delete:
            log.info("TrendTracker purged %d stale market histories", len(to_delete))
